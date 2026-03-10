import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc

# database.py からインポート
from database import (
    SessionLocal,
    MemoryItem,
    MemoryEvidence,
    MemoryView,
    MemoryHistory,
    MemoryCompactionRun,
    MemoryIngestionRun
)
from layer_a.memory_models import MemoryItemModel, MemoryStatus, MemoryAction, ViewName

logger = logging.getLogger(__name__)

def get_session() -> Session:
    return SessionLocal()

def generate_id() -> str:
    return str(uuid.uuid4())

# ===== Memory Items =====

def save_memory_item(db: Session, item_data: dict) -> MemoryItem:
    """MemoryItemを保存・更新する"""
    item_id = item_data.get("id", generate_id())
    
    # 既存チェック
    existing = db.query(MemoryItem).filter(MemoryItem.id == item_id).first()
    if existing:
        for k, v in item_data.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        item = existing
    else:
        item = MemoryItem(id=item_id, **{k: v for k, v in item_data.items() if k != "id"})
        db.add(item)
    return item

def get_active_memory_by_key(db: Session, user_id: str, key_norm: str) -> Optional[MemoryItem]:
    """特定のkeyを持つactiveなMemoryItemを取得(preferenceやstate用)"""
    return db.query(MemoryItem).filter(
        MemoryItem.user_id == user_id,
        MemoryItem.key_norm == key_norm,
        MemoryItem.status == 'active'
    ).first()

def get_active_memories(db: Session, user_id: str, memory_types: Optional[List[str]] = None) -> List[MemoryItem]:
    """ユーザーのactiveなMemoryItemを取得"""
    query = db.query(MemoryItem).filter(
        MemoryItem.user_id == user_id,
        MemoryItem.status == 'active'
    )
    if memory_types:
        query = query.filter(MemoryItem.memory_type.in_(memory_types))
    return query.all()

def mark_memory_status(db: Session, memory_id: str, status: MemoryStatus) -> Optional[MemoryItem]:
    """MemoryItemのステータスを変更する"""
    item = db.query(MemoryItem).filter(MemoryItem.id == memory_id).first()
    if item:
        item.status = status
        # statusを更新した時刻などを入れたい場合はここで処理
    return item

# ===== History & Evidence =====

def add_memory_history(
    db: Session,
    user_id: str,
    memory_id: str,
    action: MemoryAction,
    reason: Optional[str] = None,
    actor: str = "system",
    before_dict: Optional[dict] = None,
    after_dict: Optional[dict] = None
) -> MemoryHistory:
    """履歴を記録する"""
    history = MemoryHistory(
        id=generate_id(),
        user_id=user_id,
        memory_item_id=memory_id,
        action=action,
        reason=reason,
        actor=actor,
        before_json=json.dumps(before_dict, ensure_ascii=False) if before_dict else None,
        after_json=json.dumps(after_dict, ensure_ascii=False) if after_dict else None
    )
    db.add(history)
    return history

def add_memory_evidence(
    db: Session,
    memory_id: str,
    user_id: str,
    conversation_id: str,
    quote_text: Optional[str] = None,
    evidence_strength: float = 0.5
) -> MemoryEvidence:
    """証拠(evidence)を記録する"""
    evidence = MemoryEvidence(
        id=generate_id(),
        memory_item_id=memory_id,
        user_id=user_id,
        conversation_id=conversation_id,
        quote_text=quote_text,
        evidence_strength=evidence_strength,
        occurred_at=datetime.now(timezone.utc)
    )
    db.add(evidence)
    return evidence

# ===== Views =====

def save_memory_view(
    db: Session,
    user_id: str,
    view_name: ViewName,
    content_text: str,
    source_version_hash: str,
    token_estimate: int = 0
) -> MemoryView:
    """MemoryViewを保存・更新する(UPSERT的に動作)"""
    view = db.query(MemoryView).filter(
        MemoryView.user_id == user_id,
        MemoryView.view_name == view_name
    ).first()
    
    if view:
        view.content_text = content_text
        view.source_version_hash = source_version_hash
        view.token_estimate = token_estimate
        view.generated_at = datetime.now(timezone.utc)
    else:
        view = MemoryView(
            id=generate_id(),
            user_id=user_id,
            view_name=view_name,
            content_text=content_text,
            token_estimate=token_estimate,
            source_version_hash=source_version_hash,
            generated_at=datetime.now(timezone.utc)
        )
        db.add(view)
    return view

def get_memory_view(db: Session, user_id: str, view_name: ViewName) -> Optional[MemoryView]:
    """特定のMemoryViewを取得する"""
    return db.query(MemoryView).filter(
        MemoryView.user_id == user_id,
        MemoryView.view_name == view_name
    ).first()

# ===== Ingestion Runs =====

def check_ingestion_idempotency(db: Session, user_id: str, conversation_id: str, source_hash: str) -> bool:
    """すでに同じconversationと内容で処理済みか確認する"""
    run = db.query(MemoryIngestionRun).filter(
        MemoryIngestionRun.user_id == user_id,
        MemoryIngestionRun.conversation_id == conversation_id,
        MemoryIngestionRun.source_hash == source_hash,
        MemoryIngestionRun.status == 'completed'
    ).first()
    return run is not None

def start_ingestion_run(db: Session, user_id: str, conversation_id: str, source_hash: str) -> MemoryIngestionRun:
    """Ingestion開始を記録"""
    run = MemoryIngestionRun(
        id=generate_id(),
        user_id=user_id,
        conversation_id=conversation_id,
        source_hash=source_hash,
        status='started'
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

def complete_ingestion_run(db: Session, run_id: str, extracted_count: int, saved_count: int):
    """Ingestion完了を記録"""
    run = db.query(MemoryIngestionRun).filter(MemoryIngestionRun.id == run_id).first()
    if run:
        run.status = 'completed'
        run.extracted_count = extracted_count
        run.saved_count = saved_count
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

def fail_ingestion_run(db: Session, run_id: str, error_text: str):
    """Ingestion失敗を記録"""
    run = db.query(MemoryIngestionRun).filter(MemoryIngestionRun.id == run_id).first()
    if run:
        run.status = 'failed'
        run.error_text = error_text
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
