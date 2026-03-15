"""
research_engine/planner.py

Ollamaを使ったリサーチプラン生成。
セルフクリティックループ（2回）で検索クエリを改善する。
"""
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_K_M")

_SYSTEM_PROMPT = """\
あなたはPM/CM専門の技術リサーチプランナーです。
与えられた質問に対し、以下のJSONスキーマ形式のみで出力してください。
前置き・説明文・Markdownコードブロックは不要です。JSONのみ出力。
各カテゴリのqueriesは日本語の検索クエリを最大3つ。

{
  "domain": "architecture | construction | general",
  "categories": [
    {
      "id": "legal | design_guideline | manufacturer | case_study | academic",
      "name": "カテゴリ表示名",
      "queries": ["検索クエリ1", "検索クエリ2", "検索クエリ3"],
      "priority": 1,
      "trust_target": 0.9
    }
  ],
  "estimated_sources": 15,
  "key_aspects": ["注目観点1", "観点2"]
}\
"""

_CRITIQUE_PROMPT = """\
以下のプランの検索クエリを改善してください。改善後のJSONのみ出力。
{plan_json}\
"""


async def _call_ollama(prompt: str, system: str = "") -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=600.0) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()["response"]


async def generate_plan(question: str) -> dict:
    """
    質問に対するリサーチプランを生成する。
    セルフクリティックループを2回実行して検索クエリを改善する。
    """
    # 初回プラン生成
    raw = await _call_ollama(prompt=question, system=_SYSTEM_PROMPT)
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Planner: initial JSON parse failed, retrying without format hint")
        plan = {"domain": "general", "categories": [], "estimated_sources": 10, "key_aspects": []}

    # セルフクリティック（2回）
    for i in range(2):
        plan_json_str = json.dumps(plan, ensure_ascii=False)
        critique_prompt = _CRITIQUE_PROMPT.format(plan_json=plan_json_str)
        try:
            raw2 = await _call_ollama(prompt=critique_prompt, system=_SYSTEM_PROMPT)
            improved = json.loads(raw2)
            plan = improved
            logger.info(f"Planner: self-critique round {i + 1} done")
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Planner: self-critique round {i + 1} failed: {e}")
            break

    return plan
