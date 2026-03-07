import logging
from typing import Dict, Any, List
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session
from database import SessionLocal
from layer_a import memory_store
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

def regenerate_views(user_id: str, db_session: Session = None) -> Dict[str, Any]:
    """
    canonical memory から core_200 / active_300 / profile_800 を再生成する。
    """
    db = db_session or SessionLocal()
    has_own_session = db_session is None
    
    try:
        logger.info(f"Regenerating views for user {user_id}...")
        active_items = memory_store.get_active_memories(db, user_id)
        if not active_items:
            logger.info("No active memories to generate views from.")
            return {"status": "skipped", "reason": "no_active_items"}
            
        # Serialize for LLM
        memories_jsons = []
        for item in active_items:
            memories_jsons.append({
                "id": item.id,
                "type": item.memory_type,
                "key": item.key_norm,
                "content": item.canonical_text,
                "score": item.utility_score,
                "since": str(item.first_seen_at)
            })
            
        prompt_template = _load_prompt("generate_views.txt")
        prompt = prompt_template.replace("{{canonical_memories_json}}", json.dumps(memories_jsons, ensure_ascii=False))
        
        client = get_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
        )
        data = _extract_json(response.text)
        
        # Save Views
        # generate simple version hash based on item count and latest update
        latest_update = max((i.updated_at for i in active_items if i.updated_at), default=datetime.now())
        version_hash = f"v_{len(active_items)}_{latest_update.timestamp()}"
        
        if "core_200" in data:
            memory_store.save_memory_view(db, user_id, "core_200", data["core_200"], version_hash, len(data["core_200"]) // 4)
        if "active_300" in data:
            memory_store.save_memory_view(db, user_id, "active_300", data["active_300"], version_hash, len(data["active_300"]) // 4)
        if "profile_800" in data:
            memory_store.save_memory_view(db, user_id, "profile_800", data["profile_800"], version_hash, len(data["profile_800"]) // 4)
            
        db.commit()
        return {"status": "success", "views_generated": list(data.keys())}

    except Exception as e:
        logger.error(f"Error regenerating views: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        if has_own_session:
            db.close()
