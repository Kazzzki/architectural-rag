"""
research_engine/summarizer.py

Gemini Flash を使ってMarkdownソースを300文字以内に要約する。
"""
import asyncio
import logging

from config import GEMINI_MODEL_FLASH
from gemini_client import get_client

logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 12000

_SYSTEM_TEMPLATE = """\
あなたはPM/CM専門の文書要約者です。
以下の文書を300文字以内で要約してください。
カテゴリ: {category}
数値基準・判断基準・注意点を優先して抽出してください。
要約のみ出力（前置き・見出し不要）。\
"""


def _call_gemini_sync(prompt: str) -> str:
    client = get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL_FLASH,
        contents=prompt,
    )
    return response.text or ""


async def summarize_source(markdown_content: str, category: str, url: str = "") -> str:
    """
    Markdownコンテンツを300文字以内で要約して返す。
    失敗した場合は空文字を返す。
    """
    text = markdown_content[:_MAX_INPUT_CHARS]
    system = _SYSTEM_TEMPLATE.format(category=category)
    prompt = f"{system}\n\n{text}"

    try:
        return await asyncio.to_thread(_call_gemini_sync, prompt)
    except Exception as e:
        logger.warning(f"summarize_source failed [{url}]: {e}")
        return ""
