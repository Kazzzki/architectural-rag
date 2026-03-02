from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import logging

from database import SessionLocal, PersonalContext, insert_context

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Personal Context"])

class PersonalContextCreate(BaseModel):
    type: str
    content: str
    trigger_keywords: List[str] = []
    project_tag: Optional[str] = None

class PersonalContextUpdate(BaseModel):
    is_active: bool

@router.get("/api/personal-contexts")
def get_personal_contexts():
    session = SessionLocal()
    try:
        # 要件: is_active=Trueのみ、updated_at降順
        contexts = session.query(PersonalContext).filter(PersonalContext.is_active == True).order_by(PersonalContext.updated_at.desc()).all()
        result = []
        for c in contexts:
            try:
                kws = json.loads(c.trigger_keywords) if c.trigger_keywords else []
            except Exception:
                kws = []
                
            try:
                mh = json.loads(c.merge_history) if c.merge_history else []
            except Exception:
                mh = []
                
            result.append({
                "id": c.id,
                "type": c.type,
                "content": c.content,
                "trigger_keywords": kws,
                "project_tag": c.project_tag,
                "source_question": c.source_question,
                "merge_history": mh,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "is_active": c.is_active
            })
        return result
    finally:
        session.close()

@router.post("/api/personal-contexts")
def create_personal_context(data: PersonalContextCreate):
    entry = {
        "type": data.type,
        "content": data.content,
        "trigger_keywords": data.trigger_keywords,
        "project_tag": data.project_tag,
        "source_question": "Manual Entry"
    }
    try:
        new_ctx = insert_context(entry)
        return {"id": new_ctx.id, "message": "created"}
    except Exception as e:
        logger.error(f"Failed to create context manually: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/api/personal-contexts/{context_id}")
def update_personal_context_status(context_id: int, data: PersonalContextUpdate):
    session = SessionLocal()
    try:
        ctx = session.query(PersonalContext).filter(PersonalContext.id == context_id).first()
        if not ctx:
            raise HTTPException(status_code=404, detail="Not found")
        ctx.is_active = data.is_active
        session.commit()
        return {"message": "updated"}
    finally:
        session.close()

@router.delete("/api/personal-contexts/{context_id}")
def delete_personal_context(context_id: int):
    session = SessionLocal()
    try:
        ctx = session.query(PersonalContext).filter(PersonalContext.id == context_id).first()
        if not ctx:
            raise HTTPException(status_code=404, detail="Not found")
        session.delete(ctx)
        session.commit()
        return {"message": "deleted"}
    finally:
        session.close()
