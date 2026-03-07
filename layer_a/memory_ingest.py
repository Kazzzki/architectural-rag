import logging
import hashlib
import json
from typing import List, Dict, Any
from datetime import datetime

from config import MEMORY_V2_ENABLED, MEMORY_V2_WRITE_ENABLED
from database import SessionLocal
from layer_a import memory_store
from layer_a import memory_index
from layer_a.memory_extract import extract_candidates, calculate_utility_score
from layer_a.memory_merge import decide_merge_action
from layer_a.memory_models import MemoryCandidate

logger = logging.getLogger(__name__)

def generate_source_hash(messages: List[Dict[str, Any]]) -> str:
    text = "".join([m.get("content", "") for m in messages])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def ingest_conversation(
    user_id: str,
    conversation_id: str,
    messages: List[Dict[str, Any]],
    occurred_at: str | None = None,
) -> dict:
    """
    会話から memory candidates を抽出し、merge して永続化し、views を更新する。
    """
    if not MEMORY_V2_ENABLED or not MEMORY_V2_WRITE_ENABLED:
        logger.info("Memory V2 writing is disabled.")
        return {"status": "skipped", "reason": "disabled"}

    # 1. 冪等性の確認
    source_hash = generate_source_hash(messages)
    db = SessionLocal()
    try:
        if memory_store.check_ingestion_idempotency(db, user_id, conversation_id, source_hash):
            logger.info(f"Ingestion already processed for conversation={conversation_id}, source_hash={source_hash}")
            return {"status": "skipped", "reason": "idempotency"}

        # Run開始
        run = memory_store.start_ingestion_run(db, user_id, conversation_id, source_hash)

        # 会話テキストを文字列化（簡便のため）
        conv_text = ""
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            conv_text += f"{role}: {content}\n"

        # 2. Candidate Extraction
        candidates = extract_candidates(conv_text)
        extracted_count = len(candidates)
        
        saved_count = 0
        
        # 3, 4, 5. Candidate processing & Merge
        for candidate in candidates:
            # ユーティリティスコア計算
            util_score = calculate_utility_score(
                candidate.personalness,
                candidate.reusability,
                candidate.longevity,
                candidate.confidence,
                candidate.distinctiveness
            )
            
            # 既存メモリの取得 (key_norm完全一致やsemantic検索が望ましいが、ここではkey_normやtype等で簡易取得)
            existing_items = []
            if candidate.key_norm:
                active_item = memory_store.get_active_memory_by_key(db, user_id, candidate.key_norm)
                if active_item:
                    existing_items.append({
                        "id": active_item.id,
                        "memory_type": active_item.memory_type,
                        "key_norm": active_item.key_norm,
                        "canonical_text": active_item.canonical_text,
                        "value_json": active_item.value_json,
                        "support_count": active_item.support_count
                    })
            else:
                # 類義検索で既存を取得（Chromaを利用）
                search_res = memory_index.search_memory_items(
                    query=candidate.canonical_text,
                    user_id=user_id,
                    status="active",
                    limit=3
                )
                if search_res and search_res.get("metadatas"):
                    for m, d in zip(search_res["metadatas"][0], search_res["documents"][0]):
                        existing_items.append({
                            "id": m["memory_id"],
                            "memory_type": m["memory_type"],
                            "key_norm": m["key_norm"],
                            "canonical_text": d,
                            "support_count": 1 # temp
                        })

            # マージ判定
            decision = decide_merge_action(candidate, existing_items)
            action = decision.get("action", "SKIP")

            if action == "SKIP":
                continue

            target_id = decision.get("target_memory_id")
            
            new_item_data = {
                "user_id": user_id,
                "memory_type": candidate.memory_type,
                "status": "active",
                "key_norm": candidate.key_norm,
                "title": candidate.title,
                "canonical_text": candidate.canonical_text,
                "value_json": json.dumps(candidate.value_json) if candidate.value_json else None,
                "tags_json": json.dumps(candidate.tags) if candidate.tags else None,
                "entities_json": json.dumps(candidate.entities) if candidate.entities else None,
                "confidence": candidate.confidence,
                "salience": max(candidate.salience_flags != ["none"], 0.0), # 簡易
                "utility_score": util_score,
                "support_count": 1,
                "first_seen_at": datetime.now(),
                "last_seen_at": datetime.now(),
                "last_used_at": datetime.now(),
                "source_hash": source_hash
            }

            if action == "ADD":
                memory_item = memory_store.save_memory_item(db, new_item_data)
                
                # 6. Evidence保存
                memory_store.add_memory_evidence(db, memory_item.id, user_id, conversation_id, candidate.evidence_quote)
                
                # History記録
                memory_store.add_memory_history(db, user_id, memory_item.id, "add", after_dict=new_item_data)
                
                # 7. Vector Index同期
                db.commit()
                db.refresh(memory_item)
                memory_index.upsert_memory_item({c.name: getattr(memory_item, c.name) for c in memory_item.__table__.columns})
                saved_count += 1

            elif action == "MERGE_UPDATE" and target_id:
                existing_item = db.query(memory_store.MemoryItem).filter(memory_store.MemoryItem.id == target_id).first()
                if existing_item:
                    before_dict = {c.name: getattr(existing_item, c.name) for c in existing_item.__table__.columns}
                    
                    # 更新
                    if "new_memory" in decision and isinstance(decision["new_memory"], dict):
                        for k, v in decision["new_memory"].items():
                            if hasattr(existing_item, k):
                                setattr(existing_item, k, v)
                    
                    existing_item.support_count += 1
                    existing_item.last_confirmed_at = datetime.now()
                    existing_item.last_seen_at = datetime.now()
                    
                    db.commit()
                    db.refresh(existing_item)
                    
                    # Evidence保存
                    memory_store.add_memory_evidence(db, existing_item.id, user_id, conversation_id, candidate.evidence_quote)
                    
                    # History記録
                    after_dict = {c.name: getattr(existing_item, c.name) for c in existing_item.__table__.columns}
                    memory_store.add_memory_history(db, user_id, existing_item.id, "merge", before_dict=before_dict, after_dict=after_dict)
                    
                    # Vector Index同期
                    memory_index.upsert_memory_item(after_dict)
                    saved_count += 1

            elif action == "SUPERSEDE" and target_id:
                # 古いアイテムを降格
                existing_item = db.query(memory_store.MemoryItem).filter(memory_store.MemoryItem.id == target_id).first()
                if existing_item:
                    existing_item.status = "superseded"
                    before_dict = {c.name: getattr(existing_item, c.name) for c in existing_item.__table__.columns}
                    memory_store.add_memory_history(db, user_id, existing_item.id, "supersede", before_dict=before_dict)

                    # Update vector index for old item
                    db.commit()
                    db.refresh(existing_item)
                    memory_index.upsert_memory_item({c.name: getattr(existing_item, c.name) for c in existing_item.__table__.columns})

                # 新しいアイテムを作成
                new_item_data["supersedes_id"] = target_id
                
                if "new_memory" in decision and isinstance(decision["new_memory"], dict):
                        for k, v in decision["new_memory"].items():
                            if k in new_item_data:
                                new_item_data[k] = v

                memory_item = memory_store.save_memory_item(db, new_item_data)
                
                # Evidence保存
                memory_store.add_memory_evidence(db, memory_item.id, user_id, conversation_id, candidate.evidence_quote)
                
                # History記録
                memory_store.add_memory_history(db, user_id, memory_item.id, "add", after_dict=new_item_data)
                
                # Vector Index同期
                db.commit()
                db.refresh(memory_item)
                memory_index.upsert_memory_item({c.name: getattr(memory_item, c.name) for c in memory_item.__table__.columns})
                saved_count += 1

        # 8. Generated viewsの更新 (バックグラウンドタスク等で呼ぶのが望ましいが同期処理)
        from layer_a.memory_views import regenerate_views
        regenerate_views(user_id, db_session=db)

        # 完了記録
        memory_store.complete_ingestion_run(db, run.id, extracted_count, saved_count)

        return {
            "status": "completed",
            "extracted": extracted_count,
            "saved": saved_count
        }

    except Exception as e:
        logger.error(f"Error during ingest_conversation: {e}")
        if 'run' in locals() and run:
            memory_store.fail_ingestion_run(db, run.id, str(e))
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()
