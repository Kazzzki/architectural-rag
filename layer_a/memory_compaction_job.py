import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy.orm import Session
from database import SessionLocal
from layer_a import memory_store

logger = logging.getLogger(__name__)

def run_compaction(user_id: str, now_iso: str) -> Dict[str, Any]:
    """
    daily/weekly/monthly/yearly compaction を実行する。
    """
    db = SessionLocal()
    try:
        now = datetime.fromisoformat(now_iso)
        logger.info(f"Running memory compaction for user {user_id} at {now_iso}")
        
        # 1. StateのTTLチェックと降格
        stale_threshold = now - timedelta(days=30) # Default 30 days
        active_states = memory_store.get_active_memories(db, user_id, memory_types=["state"])
        demoted = 0
        for state in active_states:
            # Check last_used_at or last_confirmed_at
            last_activity = state.last_used_at or state.last_confirmed_at or state.created_at
            if last_activity < stale_threshold:
                state.status = "archived"
                memory_store.add_memory_history(db, user_id, state.id, "archive", reason="TTL expired")
                demoted += 1
                
        # 2. Compile daily summaries
        # To strictly implement daily/weekly/monthly/yearly, we would query the `memory_items` and create a `summary` type item.
        # Since this involves several LLM calls to compress, this is a skeleton for the batch job dispatcher.
        
        db.commit()
        return {
            "status": "success",
            "states_demoted": demoted,
            "summaries_generated": 0
        }
        
    except Exception as e:
        logger.error(f"Error in run_compaction: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
