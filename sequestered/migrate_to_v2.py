import logging
from database import SessionLocal, PersonalContext
from layer_a import memory_store, memory_index
from layer_a.memory_models import MemoryCandidate
from layer_a.memory_ingest import ingest_conversation

logger = logging.getLogger(__name__)

def migrate_legacy_memories():
    db = SessionLocal()
    try:
        logger.info("Starting legacy memory migration to V2...")
        legacy_items = db.query(PersonalContext).filter(PersonalContext.is_active == True).all()
        
        migrated_count = 0
        for item in legacy_items:
            # Map legacy types
            # 'judgement' -> 'principle'
            # 'lesson' -> 'episode' or 'principle'
            # 'insight' -> 'preference' or 'principle'
            
            m_type = "principle"
            if item.type == "judgement":
                m_type = "principle"
            elif item.type == "lesson":
                m_type = "episode"
            elif item.type == "insight":
                m_type = "preference"
                
            new_item_data = {
                "user_id": "default",
                "memory_type": m_type,
                "status": "active",
                "key_norm": None,
                "canonical_text": item.content,
                "tags_json": item.trigger_keywords,
                "confidence": 0.8,
                "utility_score": 0.5,
                "support_count": 1,
                "source_hash": f"legacy_{item.id}",
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            
            saved = memory_store.save_memory_item(db, new_item_data)
            db.commit()
            db.refresh(saved)
            
            if item.source_question:
                memory_store.add_memory_evidence(db, saved.id, "default", "legacy", item.source_question)
                
            memory_index.upsert_memory_item({c.name: getattr(saved, c.name) for c in saved.__table__.columns})
            migrated_count += 1
            
        logger.info(f"Successfully migrated {migrated_count} legacy memory items.")
    except Exception as e:
        logger.error(f"Error during legacy migration: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_legacy_memories()
