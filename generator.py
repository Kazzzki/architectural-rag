# generator.py - Gemini APIで回答生成（Webアプリ版）

from typing import List, Dict, Any, AsyncGenerator, Optional, Iterator, Union
from google.genai import types
from pathlib import Path
from threading import Lock
import logging

# --- v4.1: Loggerを冒頭で定義 (#9) ---
logger = logging.getLogger(__name__)

from config import GEMINI_MODEL_RAG, MAX_TOKENS, TEMPERATURE
from gemini_client import get_client
from utils.retry import sync_retry

# モデル名のマッピング（フロントエンドでの表示用IDを実際のAPIモデル名に変換）
MODEL_MAPPING = {
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite-preview",
}

def _resolve_model_name(model_name: str) -> str:
    """内部用のモデル名に変換する（マッピングがあれば適用、なければそのまま）(#8, #11)"""
    return MODEL_MAPPING.get(model_name, model_name)

# --- Layer 0: 外部ファイルからシステムプロンプトを読み込む ---
_LAYER0_PATH = Path(__file__).parent / "prompts" / "layer0_principles.md"
_LAYER_A1_PATH = Path(__file__).parent / "prompts" / "layer_a1_role_principles.md"
_FALLBACK_PROMPT = """あなたは建築意匠設計の技術アドバイザーです。（Layer 0ファイルが見つかりません）"""

# キャッシュ同期用ロック (#10)
_cache_lock = Lock()
_layer0_cache: str = ""
_layer_a1_cache: str = ""

def _load_layer0() -> str:
    """参っLayer 0ファイルを読み込む。存在しない場合はフォールバック文字列を返す。"""
    try:
        if _LAYER0_PATH.exists():
            content = _LAYER0_PATH.read_text(encoding="utf-8").strip()
            if content:
                return content
        logger.warning(f"Layer 0 file not found or empty: {_LAYER0_PATH}. Using fallback.")
    except Exception as e:
        logger.error(f"Failed to load Layer 0 file: {e}")
    return _FALLBACK_PROMPT

def _load_layer_a1() -> str:
    """「Layer A1」（安定役割原則）ファイルを読み込む。存在しない場合は空文字列を返す。"""
    try:
        if _LAYER_A1_PATH.exists():
            content = _LAYER_A1_PATH.read_text(encoding="utf-8").strip()
            if content:
                return content
        logger.warning(f"Layer A1 file not found or empty: {_LAYER_A1_PATH}. Skipping.")
    except Exception as e:
        logger.error(f"Failed to load Layer A1 file: {e}")
    return ""

# 起動時に一度読み込み、メモリにキャッシュ
with _cache_lock:
    _layer0_cache = _load_layer0()
    _layer_a1_cache = _load_layer_a1()

def reload_layer0() -> str:
    """Layer 0キャッシュをディスクから再読み込みする。API経由で呼び出す。(#10)"""
    global _layer0_cache, _layer_a1_cache
    with _cache_lock:
        _layer0_cache = _load_layer0()
        _layer_a1_cache = _load_layer_a1()
        logger.info(f"Layer 0 reloaded. chars={len(_layer0_cache)}, A1 chars={len(_layer_a1_cache)}")
        return _layer0_cache

# 互換性のため
GEMINI_MODEL = GEMINI_MODEL_RAG

# RAGなし（直接回答）用のシステムプロンプト
SYSTEM_PROMPT_DIRECT = """あなたは建築意匠設計の技術アドバイザーです。
建設プロジェクトのPM/CM（プロジェクトマネジメント/コンストラクションマネジメント）の立場から、設計者と技術的な議論ができるレベルで回答してください。

【回答ルール】
1. 技術的根拠を明示する（法令名・基準名・仕様書名を具体的に）
2. コスト・工期・メンテナンスへの影響がある場合は必ず言及する
3. 複数の選択肢がある場合は比較表形式で整理する
4. 日本の建築基準法・JIS・JASS等の日本国内基準に基づく
5. 回答は必ず日本語で行うこと
6. 知識ベースは参照しないため、出典タグ（[S番号:p.XX]）は使用しない

【注意】このモードでは社内知識ベースを参照しません。一般的な専門知識で回答します。
"""


def build_layer_b_manual_block(context_sheet: Optional[str]) -> str:
    """Layer B手動文脈をuser_promptへ注入するための整形済みブロックを返す。"""
    if not context_sheet or not context_sheet.strip():
        return ""
    return (
        "【Layer B: プロジェクトコンテキスト（手動設定）】\n"
        f"{context_sheet.strip()}\n\n"
    )

def build_system_prompt_direct() -> str:
    """RAGなしモード用システムプロンプトを返す。Layer Bはuser_prompt側で注入する。"""
    return SYSTEM_PROMPT_DIRECT

def build_system_prompt() -> str:
    """
    system_instruction に展開するコンテンツを返す。
    構成: Layer 0（常設・不変）+ Layer A1（安定役割原則）
    注意: A2（動的経験知）はここに含めず、user_prompt 側の build_a2_block() で注入する。
    """
    with _cache_lock:
        parts = [_layer0_cache]
        if _layer_a1_cache:
            parts.append(f"\n\n---\n## Layer A1: 安定役割原則\n{_layer_a1_cache}")
    return "\n".join(parts)

def build_a2_block(personal_contexts: list) -> str:
    """
    Layer A2（動的経験知）を user_prompt 向けブロックとして整形する。
    system_instruction 側には入れない。
    """
    if not personal_contexts:
        return ""
    items = "\n".join([f"- [{c['type']}] {c['content']}" for c in personal_contexts])
    return (
        "\n\n[参考: Layer A2 — 関連する過去の経験・判断基準（実経手履から取得）]\n"
        "以下は各質問に関連する過去の判断・学びです。回答の参考にしてください。\n"
        f"{items}\n"
    )

# フロントから受け取る会話履歴の1件あたりの最大文字数（長い回答を切り詰めてトークン節約）
_HISTORY_MAX_CONTENT_CHARS = 2000

def extract_web_sources_from_grounding_metadata(grounding_metadata) -> List[Dict[str, str]]:
    """Geminiのgrounding_metadataからウェブソースのタイトルとURLを抽出する"""
    if not grounding_metadata:
        return []
    
    sources = []
    seen_urls = set()
    
    # attribute形式またはdict形式の両方に対応
    chunks = getattr(grounding_metadata, 'grounding_chunks', [])
    if not chunks and isinstance(grounding_metadata, dict):
        chunks = grounding_metadata.get('grounding_chunks', [])
    
    for chunk in chunks:
        web = getattr(chunk, 'web', None)
        if web is None and isinstance(chunk, dict):
            web = chunk.get('web')
        
        if web:
            title = getattr(web, 'title', "") or (web.get('title') if isinstance(web, dict) else "")
            uri = getattr(web, 'uri', "") or (web.get('uri') if isinstance(web, dict) else "")
            
            if uri and uri not in seen_urls:
                sources.append({
                    "title": title or uri or "Untitled",
                    "url": uri
                })
                seen_urls.add(uri)
    return sources
    
def _format_sources(source_files: List[Dict[str, Any]]) -> str:
    """参照ファイル一覧をフォーマットする。source_id優先。(#6)"""
    lines = []
    for i, sf in enumerate(source_files):
        sid = sf.get('source_id')
        if not sid:
            sid = f"S{i+1}"
        lines.append(f"- [{sid}] {sf['filename']}（{sf['category']}）")
    return "\n".join(lines) if lines else "（関連ファイルなし）"

def _get_project_context(user_id: str, question: str, project_id: Optional[str], scope_mode: str) -> Dict[str, str]:
    """Layer B (プロジェクト文脈) を取得する。失敗時はログを残す。(#4, #13)"""
    try:
        from backend.scope_resolver import resolve_scope
        from backend.project_context_builder import build_project_context_block
        
        # mock_user を排除し実 user_id を使用 (#13)
        res_scope = resolve_scope(user_id, question, project_id, scope_mode)
        if res_scope["scope_type"] == "project":
            return build_project_context_block(user_id, res_scope["project_id"], question)
    except Exception as e:
        # 無音で握りつぶさず warning ログを出す (#4)
        logger.warning(f"Failed to resolve Layer B context for user {user_id}: {e}")
        
    return {"core_view": "", "active_view": "", "cross_project_lessons": ""}

def _get_tools(use_web_search: bool) -> Optional[List[types.Tool]]:
    """ツール（Google Search等）のリストを構築する。(#12)"""
    if use_web_search:
        return [types.Tool(google_search=types.GoogleSearch())]
    return None

def _get_personal_contexts(question: str) -> List[Dict[str, Any]]:
    """Layer A2 (個人知見) を取得する。"""
    try:
        from context_retriever import get_relevant_personal_contexts
        return get_relevant_personal_contexts(question)
    except Exception as e:
        logger.warning(f"Personal context retrieval failed (non-critical): {e}")
        return []


def _build_contents(
    user_prompt: str,
    history: Optional[List[Dict]] = None
) -> List[types.Content]:
    """
    会話履歴（history）と現在のユーザープロンプトを Gemini の Contents リストに変換する。
    history の role は "user" / "assistant" を想定。Gemini では "model" に変換する。
    直近 10 件（5往復）のみ使用してトークン超過を防ぐ。
    """
    contents: List[types.Content] = []

    if history:
        # 直近10件に制限（古いほど省略）
        recent = history[-10:]
        for msg in recent:
            role = "user" if msg.get("role") == "user" else "model"
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            # 長い回答は切り詰め
            if len(content) > _HISTORY_MAX_CONTENT_CHARS:
                content = content[:_HISTORY_MAX_CONTENT_CHARS] + "…（省略）"
            contents.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=content)]
            ))

    # 現在の質問を末尾に追加
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_prompt)]
    ))
    return contents


def _build_rag_user_prompt(
    question: str,
    context: str,
    source_files: List[Dict[str, Any]],
    context_sheet: Optional[str],
    project_context: Dict[str, str],
    personal_contexts: List[Dict[str, Any]]
) -> str:
    """RAG用ユーザープロンプトを構築する。v4: 出典ルール冒頭配置・空セクション除去 (#16)"""
    parts = []

    # 出典ルール（最重要 → 冒頭に配置）
    parts.append("""【回答ルール（厳守）】
1. 回答は必ず知識ベースの情報に基づくこと。知識ベースに該当情報がない場合は「知識ベースには該当する情報がありませんでした」と明示した上で、一般知識で補足すること。
2. 本文中で参照した箇所に [S番号:p.ページ番号] の形式でインラインタグを挿入すること（例: [S1:p.12]）。
3. 回答末尾に「📎 関連資料」セクションを記載すること。
4. 知識ベースの情報と一般知識を混在させない。区別して記載すること。""")

    # Layer B: プロジェクトコンテキスト（空でなければ注入）
    context_sheet_block = build_layer_b_manual_block(context_sheet)
    if context_sheet_block:
        parts.append(context_sheet_block)

    core_view = project_context.get('core_view', '')
    if core_view.strip():
        parts.append(f"【プロジェクト文脈】\n{core_view}")

    active_view = project_context.get('active_view', '')
    if active_view.strip():
        parts.append(f"【現在の論点】\n{active_view}")

    # 知識ベースコンテキスト
    if context.strip():
        parts.append(f"【知識ベースから検索された情報】\n{context}")
    else:
        parts.append("【知識ベースから検索された情報】\n（該当する情報は見つかりませんでした）")

    # 質問
    parts.append(f"【質問】\n{question}")

    # 参照ファイル一覧
    if source_files:
        source_files_formatted = _format_sources(source_files)
        parts.append(f"【参照ファイル一覧（各ファイルにはS番号が振られている）】\n{source_files_formatted}")

    # A2: 個人知見
    a2_block = build_a2_block(personal_contexts)
    if a2_block:
        parts.append(a2_block)

    return "\n\n".join(parts)

def _build_direct_user_prompt(
    question: str,
    context_sheet: Optional[str],
    project_context: Dict[str, str],
    personal_contexts: List[Dict[str, Any]]
) -> str:
    """RAGなし用ユーザープロンプトを構築する。Layer Bを注入 (#17)"""
    context_sheet_block = build_layer_b_manual_block(context_sheet)
    a2_block = build_a2_block(personal_contexts)
    
    # direct経路でもLayer Bを入れる (#17)
    return f"""{context_sheet_block}【Layer B: 現在のプロジェクト文脈（自動）】
{project_context.get('core_view', '')}

【Layer B: 現在の論点】
{project_context.get('active_view', '')}

【質問】
{question}

{a2_block}"""


@sync_retry(max_retries=3, base_wait=2.0)
def _call_gemini_generate(client, model, contents, config):
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=config
    )

@sync_retry(max_retries=3, base_wait=2.0)
def _call_gemini_stream(client, model, contents, config):
    return client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=config
    )


# ─── 統合コア: 準備・レスポンス抽出・ストリーム処理 ──────────────────────────────

def _prepare_generation(
    question: str,
    use_rag: bool,
    context: str = "",
    source_files: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "unknown_user",
    use_web_search: bool = False,
) -> tuple:
    """RAG/Direct共通の生成準備。(contents, resolved_model, config) を返す。"""
    project_context = _get_project_context(user_id, question, project_id, scope_mode)
    personal_contexts = _get_personal_contexts(question)

    if use_rag:
        user_prompt = _build_rag_user_prompt(
            question, context, source_files or [], context_sheet, project_context, personal_contexts
        )
        system_prompt = build_system_prompt()
    else:
        user_prompt = _build_direct_user_prompt(
            question, context_sheet, project_context, personal_contexts
        )
        system_prompt = build_system_prompt_direct()

    contents = _build_contents(user_prompt, history)
    resolved_model = _resolve_model_name(model)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=TEMPERATURE,
        max_output_tokens=MAX_TOKENS,
        tools=_get_tools(use_web_search),
    )
    return contents, resolved_model, config


def _extract_response(response, use_web_search: bool) -> Any:
    """Geminiレスポンスからテキストとweb_sourcesを抽出する。"""
    answer_text = response.text
    if not use_web_search:
        return answer_text
    grounding_metadata = None
    if response.candidates and response.candidates[0].grounding_metadata:
        grounding_metadata = response.candidates[0].grounding_metadata
    elif getattr(response, 'grounding_metadata', None):
        grounding_metadata = response.grounding_metadata
    web_sources = extract_web_sources_from_grounding_metadata(grounding_metadata)
    return {"answer": answer_text, "web_sources": web_sources}


def _process_stream_chunks(stream_iter, use_web_search: bool = False) -> Iterator[Dict[str, Any]]:
    """Geminiのストリームチャンクを処理し、共通フォーマットのDictをイテレートする"""
    try:
        for chunk in stream_iter:
            if chunk.text:
                yield {"type": "answer", "data": chunk.text}
            if use_web_search:
                gm = None
                if chunk.candidates and chunk.candidates[0].grounding_metadata:
                    gm = chunk.candidates[0].grounding_metadata
                if gm:
                    web_sources = extract_web_sources_from_grounding_metadata(gm)
                    if web_sources:
                        yield {"type": "web_sources", "data": web_sources}
    except Exception as e:
        logger.error(f"Stream chunk processing failed: {e}", exc_info=True)
        raise


# ─── 非ストリーミング統合コア ────────────────────────────────────────────────────

def _generate_core(
    question: str,
    use_rag: bool,
    context: str = "",
    source_files: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "unknown_user",
    use_web_search: bool = False,
) -> Any:
    """RAG/Direct共通の非ストリーミング生成コア"""
    try:
        contents, resolved_model, config = _prepare_generation(
            question, use_rag, context, source_files, history,
            model, context_sheet, project_id, scope_mode, user_id, use_web_search,
        )
        client = get_client()
        response = _call_gemini_generate(client, resolved_model, contents, config)
        return _extract_response(response, use_web_search)
    except Exception as e:
        mode = "RAG" if use_rag else "direct"
        logger.error(f"Gemini {mode} generation failed: {e}", exc_info=True)
        raise RuntimeError("AI回答生成に一時的な問題が発生しています。しばらく待ってから再試行してください。")


def _stream_core(
    question: str,
    use_rag: bool,
    context: str = "",
    source_files: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "unknown_user",
    use_web_search: bool = False,
) -> Iterator[Dict[str, Any]]:
    """RAG/Direct共通のストリーミング生成コア"""
    try:
        contents, resolved_model, config = _prepare_generation(
            question, use_rag, context, source_files, history,
            model, context_sheet, project_id, scope_mode, user_id, use_web_search,
        )
        client = get_client()
        stream_iter = _call_gemini_stream(client, resolved_model, contents, config)
        yield from _process_stream_chunks(stream_iter, use_web_search)
    except Exception as e:
        mode = "RAG" if use_rag else "direct"
        logger.error(f"Gemini {mode} stream failed: {e}", exc_info=True)
        raise


# ─── 後方互換パブリック API（既存のシグネチャを維持） ──────────────────────────────

def generate_answer(
    question: str,
    context: str,
    source_files: List[Dict[str, Any]],
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "unknown_user",
    use_web_search: bool = False,
) -> Any:
    """Gemini APIで回答を生成（会話履歴対応）"""
    return _generate_core(
        question, use_rag=True, context=context, source_files=source_files,
        history=history, model=model, context_sheet=context_sheet,
        project_id=project_id, scope_mode=scope_mode, user_id=user_id,
        use_web_search=use_web_search,
    )

def generate_answer_direct(
    question: str,
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "unknown_user",
    use_web_search: bool = False,
) -> Any:
    """RAGなし：知識ベースを参照せずLLMが直接回答する"""
    return _generate_core(
        question, use_rag=False,
        history=history, model=model, context_sheet=context_sheet,
        project_id=project_id, scope_mode=scope_mode, user_id=user_id,
        use_web_search=use_web_search,
    )

def generate_answer_stream(
    question: str,
    context: str,
    source_files: List[Dict[str, Any]],
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "unknown_user",
    use_web_search: bool = False,
) -> Iterator[Dict[str, Any]]:
    """ストリーミング形式で回答を生成（会話履歴対応）"""
    return _stream_core(
        question, use_rag=True, context=context, source_files=source_files,
        history=history, model=model, context_sheet=context_sheet,
        project_id=project_id, scope_mode=scope_mode, user_id=user_id,
        use_web_search=use_web_search,
    )

def generate_answer_stream_direct(
    question: str,
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "unknown_user",
    use_web_search: bool = False,
) -> Iterator[Dict[str, Any]]:
    """RAGなし：知識ベースを参照せずLLMが直接ストリーミング回答する"""
    return _stream_core(
        question, use_rag=False,
        history=history, model=model, context_sheet=context_sheet,
        project_id=project_id, scope_mode=scope_mode, user_id=user_id,
        use_web_search=use_web_search,
    )
