"""
research_engine/summarizer.py

Ollamaを使ってMarkdownソースを300文字以内に要約する。
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_K_M")

_MAX_INPUT_CHARS = 8000
_SYSTEM_TEMPLATE = """\
あなたはPM/CM専門の文書要約者です。
以下の文書を300文字以内で要約してください。
カテゴリ: {category}
数値基準・判断基準・注意点を優先して抽出してください。
要約のみ出力（前置き・見出し不要）。\
"""


async def summarize_source(markdown_content: str, category: str, url: str = "") -> str:
    """
    Markdownコンテンツを300文字以内で要約して返す。
    Ollama呼び出しに失敗した場合は空文字を返す。
    """
    text = markdown_content[:_MAX_INPUT_CHARS]
    system = _SYSTEM_TEMPLATE.format(category=category)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": text,
        "system": system,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=1800.0) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
    except Exception as e:
        logger.warning(f"summarize_source failed [{url}]: {e}")
        return ""
