import logging
import json
from pathlib import Path
from typing import List

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

def calculate_utility_score(personalness: float, reusability: float, longevity: float, certainty: float, distinctiveness: float) -> float:
    """utility_score算出ロジック"""
    return (
        0.30 * personalness +
        0.25 * reusability +
        0.20 * longevity +
        0.15 * certainty +
        0.10 * distinctiveness
    )

def extract_candidates(conversation_text: str) -> List[MemoryCandidate]:
    """
    LLMを使って会話から候補となるメモリ抽出とフィルタリングを行う。
    """
    prompt_template = _load_prompt("extract_candidates.txt")
    
    # Prompt構築 (SYSTEMとUSERに強引に分割するかそのまま渡す)
    # Geminiにそのまま投げるため、プロンプトを文字列置換
    prompt = prompt_template.replace("{{conversation_text}}", conversation_text)
    
    client = get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
        )
        data = _extract_json(response.text)
        candidates_raw = data.get("candidates", [])
        
        candidates = []
        for raw in candidates_raw:
            # junk判定が含まれる場合はスキップ
            if raw.get("memory_type") == "junk":
                continue
                
            # validation用
            c = MemoryCandidate(**raw)
            candidates.append(c)
            
        return candidates
        
    except Exception as e:
        logger.error(f"Error in extract_candidates: {e}")
        return []
