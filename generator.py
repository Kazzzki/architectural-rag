# generator.py - Gemini APIで回答生成（Webアプリ版）

from typing import List, Dict, Any, AsyncGenerator, Optional

from google.genai import types

from config import GEMINI_MODEL_RAG, MAX_TOKENS, TEMPERATURE
from gemini_client import get_client
from utils.retry import sync_retry
import logging

# --- Layer 0: 外部ファイルからシステムプロンプトを読み込む ---
from pathlib import Path

_LAYER0_PATH = Path(__file__).parent / "prompts" / "layer0_principles.md"
_FALLBACK_PROMPT = """あなたは建築意匠設計の技術アドバイザーです。（Layer 0ファイルが見つかりません）"""

def _load_layer0() -> str:
    """Layer 0ファイルを読み込む。存在しない場合はフォールバック文字列を返す。"""
    try:
        if _LAYER0_PATH.exists():
            content = _LAYER0_PATH.read_text(encoding="utf-8").strip()
            if content:
                return content
        logger.warning(f"Layer 0 file not found or empty: {_LAYER0_PATH}. Using fallback.")
    except Exception as e:
        logger.error(f"Failed to load Layer 0 file: {e}")
    return _FALLBACK_PROMPT

logger = logging.getLogger(__name__)

# 起動時に一度読み込み、メモリにキャッシュ
_layer0_cache: str = _load_layer0()

def reload_layer0() -> str:
    """Layer 0キャッシュをディスクから再読み込みする。API経由で呼び出す。"""
    global _layer0_cache
    _layer0_cache = _load_layer0()
    logger.info(f"Layer 0 reloaded. chars={len(_layer0_cache)}")
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


def build_system_prompt_direct(context_sheet: Optional[str] = None) -> str:
    """RAGなしモード用システムプロンプトを組み立てる。"""
    if context_sheet and context_sheet.strip():
        return SYSTEM_PROMPT_DIRECT + "\n\n---\n## 参照コンテキストシート\n" + context_sheet.strip()
    return SYSTEM_PROMPT_DIRECT


def build_system_prompt(context_sheet: Optional[str] = None) -> str:
    """Layer 0キャッシュにコンテキストシートを追記して返す。"""
    base = _layer0_cache
    if context_sheet and context_sheet.strip():
        return base + "\n\n---\n## 参照コンテキストシート\n" + context_sheet.strip()
    return base

# フロントから受け取る会話履歴の1件あたりの最大文字数（長い回答を切り詰めてトークン節約）
_HISTORY_MAX_CONTENT_CHARS = 2000


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


@sync_retry(max_retries=3, base_wait=2.0)
def _call_gemini_generate(client, model, contents, config):
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=config
    )

def generate_answer(
    question: str,
    context: str,
    source_files: List[Dict[str, Any]],
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "mock_user",  # TODO: extract real user_id
) -> str:
    """Gemini APIで回答を生成（会話履歴対応）"""

    try:
        from backend.scope_resolver import resolve_scope
        from backend.project_context_builder import build_project_context_block
        resolved_scope = resolve_scope(user_id, question, project_id, scope_mode)
        if resolved_scope["scope_type"] == "project":
            project_context = build_project_context_block(user_id, resolved_scope["project_id"], question)
        else:
            project_context = {"core_view": "", "active_view": "", "cross_project_lessons": ""}
    except Exception as e:
        logger.warning(f"Failed to resolve scope layer B: {e}")
        project_context = {"core_view": "", "active_view": "", "cross_project_lessons": ""}

    source_files_formatted = "\n".join([
        f"- [{sf['source_id']}] {sf['filename']}（{sf['category']}）"
        if sf.get('source_id')
        else f"- [S{i+1}] {sf['filename']}（{sf['category']}）"
        for i, sf in enumerate(source_files)
    ])

    if not context.strip():
        context = "（知識ベースからの検索結果はありませんでした）"

    user_prompt = f"""以下の知識ベースの情報を参照して回答してください。

【Layer B: 現在のプロジェクト文脈】
{project_context.get('core_view', '')}

【Layer B: 現在の論点】
{project_context.get('active_view', '')}

【知識ベースから検索された情報】
{context}

【質問】
{question}

【参照ファイル一覧（各ファイルにはS番号が振られている）】
{source_files_formatted if source_files_formatted.strip() else "（関連ファイルなし）"}

【出典の記載ルール】
- 本文中で参照した箇所に [S番号:p.ページ番号] の形式でインラインタグを挿入すること
- 例: 「防火区画の面積制限は1500㎡以内とされている [S1:p.12]」
- 回答末尾に「📎 関連資料」セクションも引き続き記載すること
"""

    try:
        from context_retriever import get_relevant_personal_contexts
        personal_contexts = get_relevant_personal_contexts(question)

        local_system_prompt = build_system_prompt(context_sheet)
        if personal_contexts:
            items = "\n".join([f"- [{c['type']}] {c['content']}" for c in personal_contexts])
            local_system_prompt += f"\n\n## あなた（Kazuki）の関連する経験・判断基準\n以下はこの質問に関連する、あなた自身の過去の判断や学びです。\n回答の参考にし、必要に応じて言及してください：\n\n{items}\n"

        client = get_client()
        contents = _build_contents(user_prompt, history)
        config = types.GenerateContentConfig(
            system_instruction=local_system_prompt,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_TOKENS,
        )
        response = _call_gemini_generate(client, model, contents, config)
        return response.text

    except Exception as e:
        logger.error(f"Gemini generation failed: {e}", exc_info=True)
        raise RuntimeError("AI回答生成に一時的な問題が発生しています。しばらく待ってから再試行してください。")

def generate_answer_direct(
    question: str,
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
) -> str:
    """RAGなし：知識ベースを参照せずLLMが直接回答する"""
    try:
        from context_retriever import get_relevant_personal_contexts
        personal_contexts = get_relevant_personal_contexts(question)
    except Exception as e:
        logger.warning(f"Personal context retrieval failed (non-critical): {e}")
        personal_contexts = []

    local_system_prompt = build_system_prompt_direct(context_sheet)
    if personal_contexts:
        items = "\n".join([f"- [{c['type']}] {c['content']}" for c in personal_contexts])
        local_system_prompt += f"\n\n## あなた（Kazuki）の関連する経験・判断基準\n以下はこの質問に関連する、あなた自身の過去の判断や学びです。\n回答の参考にし、必要に応じて言及してください：\n\n{items}\n"

    try:
        client = get_client()
        contents = _build_contents(question, history)
        config = types.GenerateContentConfig(
            system_instruction=local_system_prompt,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_TOKENS,
        )
        response = _call_gemini_generate(client, model, contents, config)
        return response.text
    except Exception as e:
        logger.error(f"Gemini direct generation failed: {e}", exc_info=True)
        raise RuntimeError("AI回答生成に一時的な問題が発生しています。しばらく待ってから再試行してください。")


@sync_retry(max_retries=3, base_wait=2.0)
def _call_gemini_stream(client, model, contents, config):
    # ストリームの初期化自体をリトライ可能にする
    return client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=config
    )

from typing import List, Dict, Any, Optional, Iterator

def generate_answer_stream(
    question: str,
    context: str,
    source_files: List[Dict[str, Any]],
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
    project_id: Optional[str] = None,
    scope_mode: str = "auto",
    user_id: str = "mock_user",  # TODO: extract real user_id
) -> Iterator[str]:
    """ストリーミング形式で回答を生成（会話履歴対応）"""
    try:
        try:
            from backend.scope_resolver import resolve_scope
            from backend.project_context_builder import build_project_context_block
            resolved_scope = resolve_scope(user_id, question, project_id, scope_mode)
            if resolved_scope["scope_type"] == "project":
                project_context = build_project_context_block(user_id, resolved_scope["project_id"], question)
            else:
                project_context = {"core_view": "", "active_view": "", "cross_project_lessons": ""}
        except Exception as e:
            logger.warning(f"Failed to resolve scope layer B: {e}")
            project_context = {"core_view": "", "active_view": "", "cross_project_lessons": ""}

        source_files_formatted = "\n".join([
            f"- [{sf['source_id']}] {sf['filename']}（{sf['category']}）"
            if sf.get('source_id')
            else f"- [S{i+1}] {sf['filename']}（{sf['category']}）"
            for i, sf in enumerate(source_files)
        ])

        if not context.strip():
            context = "（知識ベースからの検索結果はありませんでした）"

        user_prompt = f"""以下の知識ベースの情報を参照して回答してください。

【Layer B: 現在のプロジェクト文脈】
{project_context.get('core_view', '')}

【Layer B: 現在の論点】
{project_context.get('active_view', '')}

【知識ベースから検索された情報】
{context}

【質問】
{question}

【参照ファイル一覧（各ファイルにはS番号が振られている）】
{source_files_formatted if source_files_formatted.strip() else "（関連ファイルなし）"}

【出典の記載ルール】
- 本文中で参照した箇所に [S番号:p.ページ番号] の形式でインラインタグを挿入すること
- 例: 「防火区画の面積制限は1500㎡以内とされている [S1:p.12]」
- 回答末尾に「📎 関連資料」セクションも引き続き記載すること
"""

        try:
            from context_retriever import get_relevant_personal_contexts
            personal_contexts = get_relevant_personal_contexts(question)
        except Exception as e:
            logger.warning(f"Personal context retrieval failed (non-critical): {e}")
            personal_contexts = []

        local_system_prompt = build_system_prompt(context_sheet)
        if personal_contexts:
            items = "\n".join([f"- [{c['type']}] {c['content']}" for c in personal_contexts])
            local_system_prompt += f"\n\n## あなた（Kazuki）の関連する経験・判断基準\n以下はこの質問に関連する、あなた自身の過去の判断や学びです。\n回答の参考にし、必要に応じて言及してください：\n\n{items}\n"

        client = get_client()
        contents = _build_contents(user_prompt, history)
        config = types.GenerateContentConfig(
            system_instruction=local_system_prompt,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_TOKENS,
        )

        try:
            stream_iter = _call_gemini_stream(client, model, contents, config)
            for chunk in stream_iter:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Stream generation failed: {e}", exc_info=True)
            raise
    except Exception as e:
        logger.error(f"generate_answer_stream failed: {e}", exc_info=True)
        yield f"\n\n[生成エラー: {type(e).__name__}]"
        raise

def generate_answer_stream_direct(
    question: str,
    history: Optional[List[Dict]] = None,
    model: str = GEMINI_MODEL_RAG,
    context_sheet: Optional[str] = None,
) -> Iterator[str]:
    """RAGなし：知識ベースを参照せずLLMが直接ストリーミング回答する"""
    try:
        try:
            from context_retriever import get_relevant_personal_contexts
            personal_contexts = get_relevant_personal_contexts(question)
        except Exception as e:
            logger.warning(f"Personal context retrieval failed (non-critical): {e}")
            personal_contexts = []

        local_system_prompt = build_system_prompt_direct(context_sheet)
        if personal_contexts:
            items = "\n".join([f"- [{c['type']}] {c['content']}" for c in personal_contexts])
            local_system_prompt += f"\n\n## あなた（Kazuki）の関連する経験・判断基準\n以下はこの質問に関連する、あなた自身の過去の判断や学びです。\n回答の参考にし、必要に応じて言及してください：\n\n{items}\n"

        client = get_client()
        contents = _build_contents(question, history)
        config = types.GenerateContentConfig(
            system_instruction=local_system_prompt,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_TOKENS,
        )

        try:
            stream_iter = _call_gemini_stream(client, model, contents, config)
            for chunk in stream_iter:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Direct stream generation failed: {e}", exc_info=True)
            raise
    except Exception as e:
        logger.error(f"generate_answer_stream_direct failed: {e}", exc_info=True)
        yield f"\n\n[生成エラー: {type(e).__name__}]"
        raise
