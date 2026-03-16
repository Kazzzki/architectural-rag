"""
routers/issues.py — 課題因果グラフ API

エンドポイント:
  POST   /api/issues/capture          課題テキストをAI構造化 + 保存
  POST   /api/issues/edges/confirm    因果エッジを確定
  GET    /api/issues                  課題・エッジ一覧
  GET    /api/issues/projects         プロジェクト名一覧
  PATCH  /api/issues/{issue_id}       部分更新
  DELETE /api/issues/{issue_id}       物理削除
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Issues"])

UPDATABLE_FIELDS = {
    "status", "priority", "action_next", "is_collapsed",
    "pos_x", "pos_y", "project_name", "title", "description",
    "assignee", "context_memo",
}


# ---------- Pydantic モデル ----------

class CaptureRequest(BaseModel):
    raw_input: str
    project_name: str


class EdgeConfirmRequest(BaseModel):
    from_id: str
    to_id: str
    confirmed: bool


class IssueUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    action_next: Optional[str] = None
    is_collapsed: Optional[int] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    project_name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    assignee: Optional[str] = None
    context_memo: Optional[str] = None


class MemberCreateRequest(BaseModel):
    project_name: str
    name: str
    role: Optional[str] = None


# ---------- ヘルパー ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue_row_to_dict(row) -> dict:
    keys = [
        "id", "project_name", "title", "raw_input", "category", "priority",
        "status", "description", "cause", "impact", "action_next",
        "is_collapsed", "pos_x", "pos_y", "template_id", "created_at", "updated_at",
        "assignee", "context_memo",
    ]
    # rowの長さに合わせてキーを切り取る（古いDBとの互換性）
    return dict(zip(keys[:len(row)], row))


def _edge_row_to_dict(row) -> dict:
    keys = ["id", "from_id", "to_id", "confirmed", "created_at"]
    return dict(zip(keys, row))


def _call_gemini_capture(raw_input: str, existing_issues: list) -> dict:
    """Gemini で課題を構造化し、因果・重複候補を返す"""
    from gemini_client import get_client
    from google.genai import types

    client = get_client()

    context_lines = []
    for iss in existing_issues:
        desc = (iss["description"] or "")[:80]
        context_lines.append(f"- id={iss['id']} title={iss['title']} description={desc}")
    context_str = "\n".join(context_lines) if context_lines else "（既存課題なし）"

    prompt = f"""建設PM/CMの課題を構造化し因果・重複を分析してください。

新規課題: {raw_input}
既存課題: {context_str}

以下JSONのみ返答（各文字列フィールドは30文字以内で簡潔に）:
{{"title":"20字以内","category":"工程","priority":"normal","description":"30字以内","cause":"30字以内か空","impact":"30字以内か空","action_next":"30字以内か空","status":"発生中","causal_candidates":[],"duplicate_candidates":[]}}

- category: 工程/コスト/品質/安全
- priority: critical/normal/minor
- status: 発生中/対応中/解決済み
- causal_candidates要素: {{"issue_id":"uuid","direction":"cause_of_new","confidence":0.85,"reason":"20字以内"}}
  direction: cause_of_new=既存が原因, result_of_new=既存が結果
- duplicate_candidates要素: {{"issue_id":"uuid","similarity":0.90,"reason":"20字以内"}}
- causal_candidatesはconfidence>=0.7のみ, duplicate_candidatesはsimilarity>=0.85のみ
- 候補なければ空配列[]"""

    # gemini-3-flash-preview は max_output_tokens=1024 設定時に誤って90字で打ち切るため省略
    # thinking_level="minimal" は spec 準拠で try/except で適用
    config = types.GenerateContentConfig(
        system_instruction="建設PM/CMの課題を構造化するアシスタント。指定のJSON形式のみで返答せよ。日本語で回答。",
        temperature=0.2,
    )
    try:
        config.thinking_config = types.ThinkingConfig(
            thinking_budget_tokens=None, thinking_level="minimal"
        )
    except Exception:
        pass

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=config,
    )

    raw = response.text.strip()

    # マークダウンフェンスを除去
    import re as _re
    raw = _re.sub(r'^```(?:json)?\s*', '', raw)
    raw = _re.sub(r'\s*```$', '', raw).strip()

    # 先頭の { から末尾の } を切り出す（余計なテキストが前後にある場合の対策）
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1:
        raw = raw[start:end + 1]

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Gemini JSON parse error: {e}\nraw: {raw[:300]}")
        raise


# ---------- 再利用可能なコアロジック ----------

def capture_issue_core(raw_input: str, project_name: str, db) -> dict:
    """課題テキストをAI構造化してDBに保存し、因果・重複候補を返す。
    chat.py からも呼べるよう独立関数として定義。"""
    rows = db.execute(
        text("SELECT id, title, description FROM issues WHERE project_name = :pn"),
        {"pn": project_name},
    ).fetchall()
    existing = [{"id": r[0], "title": r[1], "description": r[2]} for r in rows]

    result = _call_gemini_capture(raw_input, existing)

    now = _now_iso()
    issue_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO issues (
                id, project_name, title, raw_input, category, priority, status,
                description, cause, impact, action_next,
                is_collapsed, pos_x, pos_y, template_id, created_at, updated_at
            ) VALUES (
                :id, :project_name, :title, :raw_input, :category, :priority, :status,
                :description, :cause, :impact, :action_next,
                0, 0.0, 0.0, NULL, :created_at, :updated_at
            )
        """),
        {
            "id": issue_id,
            "project_name": project_name,
            "title": (result.get("title") or raw_input)[:20],
            "raw_input": raw_input,
            "category": result.get("category") or "工程",
            "priority": result.get("priority") or "normal",
            "status": result.get("status") or "発生中",
            "description": result.get("description") or "",
            "cause": result.get("cause") or "",
            "impact": result.get("impact") or "",
            "action_next": result.get("action_next") or "",
            "created_at": now,
            "updated_at": now,
        },
    )
    db.commit()

    row = db.execute(
        text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}
    ).fetchone()
    issue = _issue_row_to_dict(row)

    causal_candidates = [
        c for c in result.get("causal_candidates", [])
        if isinstance(c.get("confidence"), (int, float)) and c["confidence"] >= 0.7
    ]
    duplicate_candidates = [
        c for c in result.get("duplicate_candidates", [])
        if isinstance(c.get("similarity"), (int, float)) and c["similarity"] >= 0.85
    ]

    return {
        "issue": issue,
        "causal_candidates": causal_candidates,
        "duplicate_candidates": duplicate_candidates,
    }


# ---------- エンドポイント ----------

@router.get("/api/issues/projects")
def list_projects(db=Depends(get_db)):
    """登録済みプロジェクト名のユニーク一覧"""
    rows = db.execute(
        text("SELECT DISTINCT project_name FROM issues ORDER BY project_name")
    ).fetchall()
    return {"projects": [r[0] for r in rows]}


@router.post("/api/issues/capture")
def capture_issue(req: CaptureRequest, db=Depends(get_db)):
    """課題テキストを AI で構造化して DB に保存し、因果・重複候補を返す"""
    try:
        return capture_issue_core(req.raw_input, req.project_name, db)
    except Exception as e:
        logger.error(f"Gemini capture failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI処理エラー: {str(e)}")


@router.post("/api/issues/edges/confirm")
def confirm_edge(req: EdgeConfirmRequest, db=Depends(get_db)):
    """因果関係を確認し confirmed=true の場合のみエッジを保存"""
    if not req.confirmed:
        return {"ok": True, "saved": False}

    edge_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO issue_edges (id, from_id, to_id, confirmed, created_at)
            VALUES (:id, :from_id, :to_id, 1, :created_at)
        """),
        {"id": edge_id, "from_id": req.from_id, "to_id": req.to_id, "created_at": _now_iso()},
    )
    db.commit()
    return {"ok": True, "saved": True, "edge_id": edge_id}


@router.get("/api/issues/members")
def list_members(project_name: str, db=Depends(get_db)):
    """プロジェクトメンバー一覧を返す"""
    rows = db.execute(
        text("SELECT id, project_name, name, role, created_at FROM project_members WHERE project_name = :pn ORDER BY name"),
        {"pn": project_name},
    ).fetchall()
    keys = ["id", "project_name", "name", "role", "created_at"]
    return {"members": [dict(zip(keys, r)) for r in rows]}


@router.post("/api/issues/members")
def add_member(req: MemberCreateRequest, db=Depends(get_db)):
    """プロジェクトメンバーを追加する"""
    member_id = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO project_members (id, project_name, name, role, created_at) VALUES (:id, :pn, :name, :role, :created_at)"),
        {"id": member_id, "pn": req.project_name, "name": req.name, "role": req.role, "created_at": _now_iso()},
    )
    db.commit()
    return {"id": member_id, "project_name": req.project_name, "name": req.name, "role": req.role}


@router.delete("/api/issues/members/{member_id}")
def delete_member(member_id: str, db=Depends(get_db)):
    """プロジェクトメンバーを削除する"""
    db.execute(text("DELETE FROM project_members WHERE id = :id"), {"id": member_id})
    db.commit()
    return {"ok": True}


@router.get("/api/issues")
def list_issues(
    project_name: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    db=Depends(get_db),
):
    """課題一覧 + 関連エッジ一覧 + プロジェクト名一覧を返す"""
    where_clauses = []
    params: dict = {}

    if project_name:
        where_clauses.append("project_name = :project_name")
        params["project_name"] = project_name
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    if priority:
        where_clauses.append("priority = :priority")
        params["priority"] = priority
    if category:
        where_clauses.append("category = :category")
        params["category"] = category

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    issue_rows = db.execute(
        text(f"SELECT * FROM issues {where_sql} ORDER BY created_at ASC"), params
    ).fetchall()
    issues = [_issue_row_to_dict(r) for r in issue_rows]

    # フィルター対象 issue の id セット内のエッジのみ返す
    issue_ids = {iss["id"] for iss in issues}
    if issue_ids:
        edge_rows = db.execute(text("SELECT * FROM issue_edges")).fetchall()
        edges = [
            _edge_row_to_dict(r)
            for r in edge_rows
            if r[1] in issue_ids and r[2] in issue_ids
        ]
    else:
        edges = []

    proj_rows = db.execute(
        text("SELECT DISTINCT project_name FROM issues ORDER BY project_name")
    ).fetchall()
    projects = [r[0] for r in proj_rows]

    return {"issues": issues, "edges": edges, "projects": projects}


@router.patch("/api/issues/{issue_id}")
def update_issue(issue_id: str, req: IssueUpdateRequest, db=Depends(get_db)):
    """課題の部分更新（updated_at を自動更新）"""
    updates: dict = {}
    for field in UPDATABLE_FIELDS:
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        raise HTTPException(status_code=400, detail="更新フィールドがありません")

    set_clauses = ", ".join([f"{k} = :{k}" for k in updates])
    updates["_id"] = issue_id
    updates["_updated_at"] = _now_iso()

    db.execute(
        text(f"UPDATE issues SET {set_clauses}, updated_at = :_updated_at WHERE id = :_id"),
        updates,
    )
    db.commit()

    row = db.execute(
        text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="課題が見つかりません")
    return _issue_row_to_dict(row)


@router.delete("/api/issues/{issue_id}")
def delete_issue(issue_id: str, db=Depends(get_db)):
    """課題と関連エッジを物理削除"""
    db.execute(
        text("DELETE FROM issue_edges WHERE from_id = :id OR to_id = :id"),
        {"id": issue_id},
    )
    db.execute(text("DELETE FROM issues WHERE id = :id"), {"id": issue_id})
    db.commit()
    return {"ok": True}
