import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from typing import Optional, Any, Dict, List

from database import get_db, Settings, ProjectProfile

router = APIRouter(tags=["Projects"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===== 統一プロジェクトマスター =====

class ProjectMasterCreate(BaseModel):
    name: str
    building_type: Optional[str] = None
    phase: Optional[str] = None
    scale: Optional[str] = None


class ProjectMasterUpdate(BaseModel):
    name: Optional[str] = None
    building_type: Optional[str] = None
    phase: Optional[str] = None
    scale: Optional[str] = None


def _pm_row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    return dict(row._mapping)


@router.get("/api/projects/master")
def list_projects_master(db=Depends(get_db)) -> List[Dict[str, Any]]:
    """統一プロジェクトマスター一覧"""
    rows = db.execute(text(
        "SELECT * FROM projects_master ORDER BY updated_at DESC"
    )).fetchall()
    return [_pm_row_to_dict(r) for r in rows]


@router.post("/api/projects/master", status_code=201)
def create_project_master(req: ProjectMasterCreate, db=Depends(get_db)) -> Dict[str, Any]:
    """プロジェクトマスター新規作成"""
    now = _now_iso()
    pid = str(uuid.uuid4())[:8]
    try:
        db.execute(text("""
            INSERT INTO projects_master (id, name, building_type, phase, scale, created_at, updated_at)
            VALUES (:id, :name, :bt, :phase, :scale, :ca, :ua)
        """), {
            "id": pid, "name": req.name,
            "bt": req.building_type, "phase": req.phase, "scale": req.scale,
            "ca": now, "ua": now,
        })
        db.commit()
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409, detail="同名のプロジェクトが既に存在します")
        raise
    row = db.execute(text("SELECT * FROM projects_master WHERE id = :id"), {"id": pid}).fetchone()
    return _pm_row_to_dict(row)


@router.patch("/api/projects/master/{project_id}")
def update_project_master(project_id: str, req: ProjectMasterUpdate, db=Depends(get_db)) -> Dict[str, Any]:
    """プロジェクトマスター更新"""
    existing = db.execute(
        text("SELECT id FROM projects_master WHERE id = :id"), {"id": project_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    updates: Dict[str, Any] = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.building_type is not None:
        updates["building_type"] = req.building_type
    if req.phase is not None:
        updates["phase"] = req.phase
    if req.scale is not None:
        updates["scale"] = req.scale

    if updates:
        updates["updated_at"] = _now_iso()
        updates["id"] = project_id
        set_clause = ", ".join(f"{k} = :{k}" for k in updates if k != "id")
        db.execute(text(f"UPDATE projects_master SET {set_clause} WHERE id = :id"), updates)
        db.commit()

    row = db.execute(text("SELECT * FROM projects_master WHERE id = :id"), {"id": project_id}).fetchone()
    return _pm_row_to_dict(row)

class ActiveScopeRequest(BaseModel):
    project_id: Optional[str] = None
    scope_mode: str = "auto"

@router.get("/api/system/active-scope")
def get_active_scope(db = Depends(get_db)):
    project_id_setting = db.query(Settings).filter(Settings.key == "active_project_id").first()
    scope_mode_setting = db.query(Settings).filter(Settings.key == "active_scope_mode").first()
    
    project_id = project_id_setting.value if project_id_setting else None
    scope_mode = scope_mode_setting.value if scope_mode_setting else "auto"
    
    from backend.scope_resolver import get_project_registry
    p = get_project_registry(project_id) if project_id else None
    
    return {
        "project_id": project_id,
        "scope_mode": scope_mode,
        "project_name": p["name"] if p else None,
        "source": "settings"
    }

@router.post("/api/system/active-scope")
def set_active_scope(req: ActiveScopeRequest, db = Depends(get_db)):
    for key, val in [("active_project_id", req.project_id), ("active_scope_mode", req.scope_mode)]:
        setting = db.query(Settings).filter(Settings.key == key).first()
        if not setting:
            setting = Settings(key=key, value=val or "")
            db.add(setting)
        else:
            setting.value = val or ""
    db.commit()
    return {"ok": True}

@router.get("/api/mindmap/projects")
def get_projects():
    # Mock for P1
    return {"projects": [
        {"id": "abc123", "name": "○○ビル新築", "status": "active", "building_type": "オフィス"},
        {"id": "def456", "name": "リノベ案件X", "status": "active", "building_type": "商業"},
    ]}

class ProjectProfileUpdateRequest(BaseModel):
    phase: Optional[str] = ""
    order_type: Optional[str] = ""
    client: Optional[str] = ""
    objective: Optional[str] = ""
    key_constraints: Optional[str] = ""
    current_priority: Optional[str] = ""
    current_issues: Optional[str] = ""
    rag_notes: Optional[str] = ""

@router.get("/api/projects/{project_id}/profile")
def get_project_profile_endpoint(project_id: str, db = Depends(get_db)):
    user_id = "mock_user"
    profile = db.query(ProjectProfile).filter(ProjectProfile.project_id == project_id, ProjectProfile.user_id == user_id).first()
    if not profile:
        return {
            "project_id": project_id,
            "phase": "",
            "order_type": "",
            "client": "",
            "objective": "",
            "key_constraints": "",
            "current_priority": "",
            "current_issues": "",
            "rag_notes": ""
        }
    return {
        "project_id": profile.project_id,
        "phase": profile.phase,
        "order_type": profile.order_type,
        "client": profile.client,
        "objective": profile.objective,
        "key_constraints": profile.key_constraints,
        "current_priority": profile.current_priority,
        "current_issues": profile.current_issues,
        "rag_notes": profile.rag_notes
    }

@router.put("/api/projects/{project_id}/profile")
def update_project_profile_endpoint(project_id: str, req: ProjectProfileUpdateRequest, db = Depends(get_db)):
    user_id = "mock_user"
    profile = db.query(ProjectProfile).filter(ProjectProfile.project_id == project_id, ProjectProfile.user_id == user_id).first()
    if not profile:
        profile = ProjectProfile(project_id=project_id, user_id=user_id)
        db.add(profile)
    
    if req.phase is not None: profile.phase = req.phase
    if req.order_type is not None: profile.order_type = req.order_type
    if req.client is not None: profile.client = req.client
    if req.objective is not None: profile.objective = req.objective
    if req.key_constraints is not None: profile.key_constraints = req.key_constraints
    if req.current_priority is not None: profile.current_priority = req.current_priority
    if req.current_issues is not None: profile.current_issues = req.current_issues
    if req.rag_notes is not None: profile.rag_notes = req.rag_notes
    
    db.commit()
    return {"ok": True, "project_id": project_id}
