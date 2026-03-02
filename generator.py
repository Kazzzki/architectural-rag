# generator.py - Gemini APIで回答生成（Webアプリ版）

from typing import List, Dict, Any, AsyncGenerator, Optional

from google.genai import types

from config import GEMINI_MODEL_RAG, MAX_TOKENS, TEMPERATURE
from gemini_client import get_client
from utils.retry import sync_retry
import logging

logger = logging.getLogger(__name__)

# 互換性のため
GEMINI_MODEL = GEMINI_MODEL_RAG


SYSTEM_PROMPT = """あなたは建築意匠設計の技術アドバイザーです。
建設プロジェクトのPM/CM（プロジェクトマネジメント/コンストラクションマネジメント）の立場から、設計者と技術的な議論ができるレベルで回答してください。

【回答ルール】
1. 技術的根拠を明示する（法令名・基準名・仕様書名を具体的に）
2. コスト・工期・メンテナンスへの影響がある場合は必ず言及する
3. 複数の選択肢がある場合は比較表形式で整理する
4. 知識ベースの情報で回答できない場合は、その旨を正直に伝える
5. 回答の最後に「📎 関連資料」セクションを必ず設ける
6. 日本の建築基準法・JIS・JASS等の日本国内基準に基づく
7. 回答は必ず日本語で行うこと
8. 出典には必ず「ファイル名 (p.XX)」の形式でページ番号を明記する
9. 図面（doc_type=drawing）からの出典には「📐」アイコンを付与する

【出力フォーマット】
回答本文
（Markdown形式、見出し・箇条書き・表を適宜使用）

📎 関連資料:
- [ファイル名]（カテゴリ）p.XX
- 📐 [図面ファイル名]（図面）p.XX
"""


def build_system_prompt(context_sheet: Optional[str] = None) -> str:
    """ベースのシステムプロンプトにコンテキストシートを注入して返す。"""
    if context_sheet and context_sheet.strip():
        return SYSTEM_PROMPT + "\n\n---\n## 参照コンテキストシート\n" + context_sheet.strip()
    return SYSTEM_PROMPT

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
) -> str:
    """Gemini APIで回答を生成（会話履歴対応）"""

    source_files_formatted = "\n".join([
        f"- {file['filename']}（{file['category']}）"
        for file in source_files
    ])

    if not context.strip():
        context = "（知識ベースからの検索結果はありませんでした）"

    user_prompt = f"""以下の知識ベースの情報を参照して回答してください。

【知識ベースから検索された情報】
{context}

【質問】
{question}

【利用可能な関連ファイル（回答末尾の「📎 関連資料」に含めること）】
{source_files_formatted if source_files_formatted.strip() else "（関連ファイルなし）"}
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
) -> Iterator[str]:
    """ストリーミング形式で回答を生成（会話履歴対応）"""

    source_files_formatted = "\n".join([
        f"- {file['filename']}（{file['category']}）"
        for file in source_files
    ])

    if not context.strip():
        context = "（知識ベースからの検索結果はありませんでした）"

    user_prompt = f"""以下の知識ベースの情報を参照して回答してください。

【知識ベースから検索された情報】
{context}

【質問】
{question}

【利用可能な関連ファイル（回答末尾の「📎 関連資料」に含めること）】
{source_files_formatted if source_files_formatted.strip() else "（関連ファイルなし）"}
"""

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

    stream_iter = _call_gemini_stream(client, model, contents, config)
    for chunk in stream_iter:
        if chunk.text:
            yield chunk.text
