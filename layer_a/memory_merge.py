import logging
import json
from pathlib import Path
from typing import Dict, Any, List

from gemini_client import get_client
from config import GEMINI_MODEL_RAG
from layer_a.memory_models import MemoryCandidate

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

def decide_merge_action(candidate: MemoryCandidate, existing_memories: List[dict]) -> Dict[str, Any]:
    """
    既存のメモリと新しい候補を照合し、LLMに統合判定を行わせる
    戻り値:
        action: 'SKIP' | 'ADD' | 'MERGE_UPDATE' | 'SUPERSEDE'
        target_memory_id: 更新/上書き対象のID
        updated_fields: 更新がある場合のフィールド
        new_memory: 統合された新しいメモリの内容 (MERGE_UPDATE/SUPERSEDE用)
    """
    if not existing_memories:
        return {"action": "ADD"}

    prompt_template = _load_prompt("merge_memory.txt")
    candidate_json = candidate.model_dump_json()
    existing_memories_json = json.dumps(existing_memories, ensure_ascii=False)

    prompt = prompt_template.replace("{{candidate_json}}", candidate_json)
    prompt = prompt.replace("{{existing_memories_json}}", existing_memories_json)

    client = get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
        )
        data = _extract_json(response.text)
        return data
        
    except Exception as e:
        logger.error(f"Error in decide_merge_action: {e}")
        # LLMエラー時は安全側に倒して追加 (またはSKIP) する。
        # 仕様に従って自信なき場合はSKIPを優先。
        return {"action": "SKIP"}
