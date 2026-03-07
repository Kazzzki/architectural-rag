import logging
import json
from pathlib import Path
from typing import Dict, Any

from gemini_client import get_client
from config import GEMINI_MODEL_RAG

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

def _load_prompt(filename: str) -> str:
    path = PROMPT_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _extract_json(text: str) -> dict:
    if "```json" in text:
        json_str = text.split("```json")[-1].split("```")[0].strip()
    elif "```" in text:
        json_str = text.split("```")[-1].split("```")[0].strip()
    else:
        json_str = text.strip()
    return json.loads(json_str)

def route_query(query: str) -> Dict[str, Any]:
    """
    LLMを使ってクエリを解析し、検索要件を生成する。
    戻り値:
        needs_profile: core_200 (常にTrue寄り) や profile_800 が必要か
        needs_active_state: active_300 が必要か
        memory_types: []
        time_scope: none/recent/quarter/year/all
        retrieval_goal: personalize/decision_support/project_context/timeline/style_only/none
        suggested_token_budget: int
    """
    prompt_template = _load_prompt("route_query.txt")
    prompt = prompt_template.replace("{{query}}", query)

    client = get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
        )
        data = _extract_json(response.text)
        
        # デフォルト補完
        if "needs_profile" not in data:
            data["needs_profile"] = True
        if "memory_types" not in data:
            data["memory_types"] = ["preference", "principle", "state", "episode"]
            
        return data
        
    except Exception as e:
        logger.error(f"Error in route_query: {e}")
        # フォールバック
        return {
            "needs_profile": True,
            "needs_active_state": True,
            "memory_types": ["preference", "principle", "state"],
            "time_scope": "all",
            "retrieval_goal": "decision_support",
            "suggested_token_budget": 900
        }
