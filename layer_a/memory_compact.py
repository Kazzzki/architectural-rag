import logging
import json
from pathlib import Path
from typing import Dict, Any, List

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

def compact_retrieved_context(query: str, retrieved_memories: List[dict]) -> Dict[str, Any]:
    """
    検索されたメモリを、質問に必要な範囲で短く圧縮する。
    戻り値:
        context_capsule: str
        cited_memory_ids: []
        uncertainty_notes: str
    """
    if not retrieved_memories:
        return {
            "context_capsule": "",
            "cited_memory_ids": [],
            "uncertainty_notes": None
        }

    prompt_template = _load_prompt("compact_context.txt")
    prompt = prompt_template.replace("{{query}}", query)
    prompt = prompt.replace("{{retrieved_memories_json}}", json.dumps(retrieved_memories, ensure_ascii=False))

    client = get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
        )
        data = _extract_json(response.text)
        return {"context_capsule": data.get("context_capsule", ""),
                "cited_memory_ids": data.get("cited_memory_ids", []),
                "uncertainty_notes": data.get("uncertainty_notes")}
    except Exception as e:
        logger.error(f"Error in compact_retrieved_context: {e}")
        # fallback to naive concatenation for robustness
        naive_text = "\n".join([m.get("document", "") for m in retrieved_memories])
        ids = [m.get("metadata", {}).get("memory_id") for m in retrieved_memories]
        # truncate safely
        naive_text = naive_text[:1000]
        return {
            "context_capsule": f"[Fallback Compact]\n{naive_text}",
            "cited_memory_ids": ids,
            "uncertainty_notes": "Compression failed."
        }
