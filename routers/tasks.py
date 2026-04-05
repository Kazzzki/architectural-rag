"""
routers/tasks.py — タスク管理 API

エンドポイント:
  GET    /api/tasks                         一覧取得（status/category_id/priority フィルタ）
  POST   /api/tasks                         タスク作成
  GET    /api/tasks/{id}                    詳細取得（コメント・リマインダー含む）
  PUT    /api/tasks/{id}                    更新
  DELETE /api/tasks/{id}                    削除
  GET    /api/categories                    カテゴリ一覧
  POST   /api/categories                    カテゴリ作成
  POST   /api/tasks/{id}/comments           コメント追加
  POST   /api/tasks/{id}/reminders          リマインダー追加
  GET    /api/tasks/reminders/pending       未送信リマインダー一覧（取得と同時に送信済みマーク）
  POST   /api/tasks/chat                    Gemini AI でテキスト解析 → タスク/リマインダー自動作成
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from config import GEMINI_MODEL_RAG
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Tasks"])


# ===== ヘルパー =====

# 共通: タスク詳細SELECT（ラベル・マイルストーン・リマインダー情報含む）
_TASK_DETAIL_SELECT = """
    SELECT t.*, c.name AS category_name, c.color AS category_color,
        m.name AS milestone_name,
        (SELECT GROUP_CONCAT(tl.name, ',') FROM task_label_map tlm
         JOIN task_labels tl ON tlm.label_id = tl.id
         WHERE tlm.task_id = t.id) AS label_names,
        (SELECT GROUP_CONCAT(tl.color, ',') FROM task_label_map tlm
         JOIN task_labels tl ON tlm.label_id = tl.id
         WHERE tlm.task_id = t.id) AS label_colors,
        (SELECT GROUP_CONCAT(CAST(tl.id AS TEXT), ',') FROM task_label_map tlm
         JOIN task_labels tl ON tlm.label_id = tl.id
         WHERE tlm.task_id = t.id) AS label_ids,
        CASE WHEN EXISTS (
            SELECT 1 FROM task_reminders r
            WHERE r.task_id = t.id AND r.is_sent = 0
              AND r.remind_at >= :day_start AND r.remind_at < :day_end
        ) THEN 1 ELSE 0 END AS has_today_reminder
    FROM tasks t
    LEFT JOIN task_categories c ON t.category_id = c.id
    LEFT JOIN task_milestones m ON t.milestone_id = m.id
"""


def _today_params() -> Dict[str, str]:
    """has_today_reminder 用の日付パラメータを返す"""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {"day_start": f"{today_str}T00:00:00+00:00", "day_end": f"{today_str}T23:59:59+00:00"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _upsert_auto_reminder(task_id: int, task_title: str, due_date: str, db) -> None:
    """due_date の当日 09:00 JST (= UTC 00:00) に auto-reminder を生成。既存の未送信当日リマインダーがあればスキップ。"""
    existing = db.execute(
        text("""
            SELECT id FROM task_reminders
            WHERE task_id = :task_id AND is_sent = 0
              AND remind_at >= :day_start AND remind_at < :day_end
        """),
        {
            "task_id":   task_id,
            "day_start": f"{due_date}T00:00:00+00:00",
            "day_end":   f"{due_date}T23:59:59+00:00",
        },
    ).fetchone()
    if not existing:
        db.execute(
            text("""
                INSERT INTO task_reminders (task_id, remind_at, message, is_sent, created_at)
                VALUES (:task_id, :remind_at, :message, 0, :created_at)
            """),
            {
                "task_id":   task_id,
                "remind_at": f"{due_date}T00:00:00+00:00",
                "message":   f"「{task_title}」の期限日です",
                "created_at": _now_iso(),
            },
        )


def _delete_auto_reminder(task_id: int, db) -> None:
    """未送信の自動生成リマインダー（メッセージが '〜の期限日です' で終わるもの）を削除"""
    db.execute(
        text("""
            DELETE FROM task_reminders
            WHERE task_id = :task_id AND is_sent = 0
              AND message LIKE '%の期限日です'
        """),
        {"task_id": task_id},
    )


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    return dict(row._mapping)


# ===== Pydantic モデル =====

class CategoryCreate(BaseModel):
    name: str
    color: str = "#6366f1"


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    category_id: Optional[int] = None
    due_date: Optional[str] = None
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    project_name: Optional[str] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    parent_id: Optional[int] = None
    milestone_id: Optional[int] = None
    start_date: Optional[str] = None
    source_meeting_id: Optional[int] = None
    source_type: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    category_id: Optional[int] = None
    due_date: Optional[str] = None
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    project_name: Optional[str] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    parent_id: Optional[int] = None
    milestone_id: Optional[int] = None
    start_date: Optional[str] = None


class CommentCreate(BaseModel):
    content: str


class ReminderCreate(BaseModel):
    remind_at: str
    message: Optional[str] = None


class TaskChatRequest(BaseModel):
    message: str


class BulkUpdateRequest(BaseModel):
    task_ids: List[int]
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None


class BulkCreateRequest(BaseModel):
    tasks: List[TaskCreate]


class LabelCreate(BaseModel):
    name: str
    color: str = "#6366f1"


class LabelAttach(BaseModel):
    label_ids: List[int]


class MilestoneCreate(BaseModel):
    project_name: str
    name: str
    target_date: Optional[str] = None
    status: str = "pending"
    sort_order: int = 0


class MilestoneUpdate(BaseModel):
    name: Optional[str] = None
    target_date: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


class RecurrenceCreate(BaseModel):
    rrule_type: str = "weekly"
    interval_value: int = 1
    day_of_week: Optional[str] = None
    day_of_month: Optional[int] = None


class MeetingExtractRequest(BaseModel):
    meeting_id: int


class ReportGenerateRequest(BaseModel):
    period: str = "weekly"
    project_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# ===== ヘルパー（進捗再計算） =====

def _recalc_progress(parent_id: int, db) -> None:
    """親タスクの progress を子タスクのステータスから再計算"""
    if not parent_id:
        return
    children = db.execute(
        text("SELECT status FROM tasks WHERE parent_id = :pid"),
        {"pid": parent_id},
    ).fetchall()
    if not children:
        return
    total = len(children)
    done = sum(1 for c in children if c[0] == "done")
    progress = int((done / total) * 100)
    db.execute(
        text("UPDATE tasks SET progress = :progress, updated_at = :now WHERE id = :id"),
        {"progress": progress, "now": _now_iso(), "id": parent_id},
    )
    db.commit()


def _check_parent_depth(parent_id: int, db, max_depth: int = 3) -> int:
    """親チェーンの深さを返す。max_depth 超で HTTPException"""
    depth = 0
    current = parent_id
    while current:
        depth += 1
        if depth > max_depth:
            raise HTTPException(status_code=400, detail=f"サブタスクの最大ネスト深度({max_depth})を超えています")
        row = db.execute(
            text("SELECT parent_id FROM tasks WHERE id = :id"), {"id": current}
        ).fetchone()
        if not row:
            break
        current = row[0]
    return depth


# ===== カテゴリ =====

@router.get("/api/task-categories")
def get_categories(db=Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.execute(
        text("SELECT * FROM task_categories ORDER BY name")
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/api/task-categories", status_code=201)
def create_category(req: CategoryCreate, db=Depends(get_db)) -> Dict[str, Any]:
    now = _now_iso()
    result = db.execute(
        text("INSERT INTO task_categories (name, color, created_at) VALUES (:name, :color, :created_at)"),
        {"name": req.name, "color": req.color, "created_at": now},
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM task_categories WHERE id = :id"),
        {"id": result.lastrowid},
    ).fetchone()
    return _row_to_dict(row)


# ===== リマインダー（/api/tasks/{id} より前に定義） =====

@router.get("/api/tasks/reminders/pending")
def get_pending_reminders(db=Depends(get_db)) -> List[Dict[str, Any]]:
    """未送信リマインダーを取得し、同時に is_sent=1 にマーク"""
    now = _now_iso()
    # SELECT と UPDATE を同一トランザクション内で実行（SQLiteはシリアライズされるため安全）
    rows = db.execute(
        text("""
            SELECT r.*, t.title AS task_title
            FROM task_reminders r
            JOIN tasks t ON r.task_id = t.id
            WHERE r.is_sent = 0 AND r.remind_at <= :now
        """),
        {"now": now},
    ).fetchall()
    result = [_row_to_dict(r) for r in rows]
    if result:
        ids = [item["id"] for item in result]
        id_params = {f"id_{i}": rid for i, rid in enumerate(ids)}
        id_placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
        db.execute(
            text(f"UPDATE task_reminders SET is_sent = 1 WHERE id IN ({id_placeholders})"),
            id_params,
        )
        db.commit()
    return result


# ===== AI チャット（/api/tasks/{id} より前に定義） =====

@router.post("/api/tasks/chat")
def task_chat(req: TaskChatRequest, db=Depends(get_db)) -> Dict[str, Any]:
    """Gemini でユーザーのテキストを解析し、タスク作成 or リマインダー設定を自動実行"""
    from gemini_client import get_client

    now = datetime.now(timezone.utc)

    # カテゴリ一覧を取得してプロンプトに渡す
    cats = db.execute(text("SELECT id, name FROM task_categories")).fetchall()
    cats_list = [{"id": r[0], "name": r[1]} for r in cats]

    jst_now = now + timedelta(hours=9)
    today_jst     = jst_now.strftime("%Y-%m-%d")
    tomorrow_jst  = (jst_now + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after_jst = (jst_now + timedelta(days=2)).strftime("%Y-%m-%d")
    # 今週金曜日 (weekday: 0=Mon, 4=Fri)
    days_to_friday = (4 - jst_now.weekday()) % 7
    friday_jst = (jst_now + timedelta(days=days_to_friday if days_to_friday > 0 else 7)).strftime("%Y-%m-%d")

    prompt = f"""あなたはタスク管理アシスタントです。ユーザーの日本語テキストを解析して、
適切なアクションを判断し、JSONのみを返してください。

ユーザーのテキスト: "{req.message}"
現在日時 (UTC ISO): {now.isoformat()}
現在の日本時間: {jst_now.strftime('%Y-%m-%d %H:%M')} JST
利用可能なカテゴリ: {json.dumps(cats_list, ensure_ascii=False)}

【日付変換ルール】
- 「今日」= {today_jst}
- 「明日」= {tomorrow_jst}
- 「明後日」= {day_after_jst}
- 「今週中」「今週末」= {friday_jst}
- 時刻は JST として解釈し UTC に変換（例: JST 10:00 → UTC 01:00、due_dateはYYYY-MM-DD形式）

【優先度ルール】
- 「urgent」「急ぎ」「至急」「重要」「すぐ」などのキーワードがあれば priority: "high"
- 明示的な指定がなければ priority: "medium"

【アクション選択ルール（以下の3種類から選択）】

1. タスク作成のみ:
{{"action": "create_task", "title": "タスクタイトル", "description": "説明（省略可、なければnull）", "priority": "low|medium|high", "category_id": null, "due_date": "YYYY-MM-DD または null", "estimated_minutes": null, "project_name": "プロジェクト名（言及があればセット、なければnull）", "assignee_name": "担当者名（言及があればセット、なければnull）"}}

2. リマインダー設定のみ（既存タスクへ）:
{{"action": "create_reminder", "task_title": "対象タスクのタイトル", "remind_at": "YYYY-MM-DDTHH:MM:SS+00:00", "message": "リマインダーメッセージ"}}

3. タスク作成＋リマインダー設定（「〇〇して、△時にリマインドして」など両方の意図がある場合）:
{{"action": "create_task_with_reminder", "title": "タスクタイトル", "description": null, "priority": "medium", "category_id": null, "due_date": "YYYY-MM-DD または null", "estimated_minutes": null, "project_name": null, "assignee_name": null, "remind_at": "YYYY-MM-DDTHH:MM:SS+00:00", "message": "リマインダーメッセージ"}}

判断が難しい場合はタスク作成（action: "create_task"）を選択してください。JSONのみ返してください。"""

    try:
        client = get_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
        )
        raw = response.text.strip()
        # コードブロック除去
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        parsed = json.loads(raw)
    except Exception as e:
        logger.error(f"Gemini task chat error: {e}")
        raise HTTPException(status_code=500, detail=f"AI解析エラー: {e}")

    now_iso = _now_iso()
    action = parsed.get("action")

    if action == "create_task":
        result = db.execute(
            text("""
                INSERT INTO tasks (title, description, status, priority, category_id, due_date,
                                   estimated_minutes, project_name, assignee_name, created_at, updated_at)
                VALUES (:title, :description, 'todo', :priority, :category_id, :due_date,
                        :estimated_minutes, :project_name, :assignee_name, :created_at, :updated_at)
            """),
            {
                "title": parsed.get("title", req.message[:50]),
                "description": parsed.get("description"),
                "priority": parsed.get("priority", "medium"),
                "category_id": parsed.get("category_id"),
                "due_date": parsed.get("due_date"),
                "estimated_minutes": parsed.get("estimated_minutes"),
                "project_name": parsed.get("project_name"),
                "assignee_name": parsed.get("assignee_name"),
                "created_at": now_iso,
                "updated_at": now_iso,
            },
        )
        db.commit()
        task_row = db.execute(
            text(_TASK_DETAIL_SELECT + " WHERE t.id = :id"),
            {"id": result.lastrowid, **_today_params()},
        ).fetchone()
        title = parsed.get("title", "")
        return {"action": "create_task", "task": _row_to_dict(task_row), "message": f"タスク「{title}」を作成しました"}

    elif action == "create_task_with_reminder":
        task_result = db.execute(
            text("""
                INSERT INTO tasks (title, description, status, priority, category_id, due_date,
                                   estimated_minutes, project_name, assignee_name, created_at, updated_at)
                VALUES (:title, :description, 'todo', :priority, :category_id, :due_date,
                        :estimated_minutes, :project_name, :assignee_name, :created_at, :updated_at)
            """),
            {
                "title": parsed.get("title", req.message[:50]),
                "description": parsed.get("description"),
                "priority": parsed.get("priority", "medium"),
                "category_id": parsed.get("category_id"),
                "due_date": parsed.get("due_date"),
                "estimated_minutes": parsed.get("estimated_minutes"),
                "project_name": parsed.get("project_name"),
                "assignee_name": parsed.get("assignee_name"),
                "created_at": now_iso,
                "updated_at": now_iso,
            },
        )
        db.commit()
        new_task_id = task_result.lastrowid
        task_title = parsed.get("title", req.message[:50])
        db.execute(
            text("""
                INSERT INTO task_reminders (task_id, remind_at, message, is_sent, created_at)
                VALUES (:task_id, :remind_at, :message, 0, :created_at)
            """),
            {
                "task_id":   new_task_id,
                "remind_at": parsed.get("remind_at", now_iso),
                "message":   parsed.get("message", "リマインダー"),
                "created_at": now_iso,
            },
        )
        db.commit()
        remind_at = parsed.get("remind_at", "")
        return {
            "action": "create_task_with_reminder",
            "message": f"タスク「{task_title}」を作成し、{remind_at[:16].replace('T', ' ')} UTC にリマインダーを設定しました",
        }

    elif action == "create_reminder":
        task_title = parsed.get("task_title", req.message[:50])
        # 既存タスクを曖昧検索
        task_row = db.execute(
            text("SELECT id FROM tasks WHERE title LIKE :title ORDER BY created_at DESC LIMIT 1"),
            {"title": f"%{task_title}%"},
        ).fetchone()

        if task_row:
            task_id = task_row[0]
        else:
            # 新規タスクを作成
            res = db.execute(
                text("""
                    INSERT INTO tasks (title, status, priority, created_at, updated_at)
                    VALUES (:title, 'todo', 'medium', :created_at, :updated_at)
                """),
                {"title": task_title, "created_at": now_iso, "updated_at": now_iso},
            )
            db.commit()
            task_id = res.lastrowid

        db.execute(
            text("""
                INSERT INTO task_reminders (task_id, remind_at, message, is_sent, created_at)
                VALUES (:task_id, :remind_at, :message, 0, :created_at)
            """),
            {
                "task_id": task_id,
                "remind_at": parsed.get("remind_at", now_iso),
                "message": parsed.get("message", "リマインダー"),
                "created_at": now_iso,
            },
        )
        db.commit()
        remind_at = parsed.get("remind_at", "")
        return {"action": "create_reminder", "message": f"リマインダーを設定しました: {remind_at}"}

    else:
        raise HTTPException(status_code=400, detail="テキストを解析できませんでした")


# ===== ラベル CRUD =====

@router.get("/api/task-labels")
def get_labels(db=Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.execute(
        text("SELECT * FROM task_labels ORDER BY name")
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/api/task-labels", status_code=201)
def create_label(req: LabelCreate, db=Depends(get_db)) -> Dict[str, Any]:
    now = _now_iso()
    result = db.execute(
        text("INSERT INTO task_labels (name, color, created_at) VALUES (:name, :color, :created_at)"),
        {"name": req.name, "color": req.color, "created_at": now},
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM task_labels WHERE id = :id"), {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


# ===== マイルストーン CRUD =====

@router.get("/api/task-milestones")
def get_milestones(
    project_name: Optional[str] = Query(None),
    db=Depends(get_db),
) -> List[Dict[str, Any]]:
    if project_name:
        rows = db.execute(
            text("SELECT * FROM task_milestones WHERE project_name = :pn ORDER BY sort_order, target_date"),
            {"pn": project_name},
        ).fetchall()
    else:
        rows = db.execute(
            text("SELECT * FROM task_milestones ORDER BY project_name, sort_order, target_date")
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/api/task-milestones", status_code=201)
def create_milestone(req: MilestoneCreate, db=Depends(get_db)) -> Dict[str, Any]:
    now = _now_iso()
    result = db.execute(
        text("""
            INSERT INTO task_milestones (project_name, name, target_date, status, sort_order, created_at, updated_at)
            VALUES (:project_name, :name, :target_date, :status, :sort_order, :created_at, :updated_at)
        """),
        {
            "project_name": req.project_name,
            "name": req.name,
            "target_date": req.target_date,
            "status": req.status,
            "sort_order": req.sort_order,
            "created_at": now,
            "updated_at": now,
        },
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM task_milestones WHERE id = :id"), {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


@router.put("/api/task-milestones/{milestone_id}")
def update_milestone(milestone_id: int, req: MilestoneUpdate, db=Depends(get_db)) -> Dict[str, Any]:
    existing = db.execute(
        text("SELECT id FROM task_milestones WHERE id = :id"), {"id": milestone_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="マイルストーンが見つかりません")
    updates: Dict[str, Any] = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.target_date is not None:
        updates["target_date"] = req.target_date
    if req.status is not None:
        updates["status"] = req.status
    if req.sort_order is not None:
        updates["sort_order"] = req.sort_order
    if updates:
        updates["updated_at"] = _now_iso()
        updates["id"] = milestone_id
        set_clause = ", ".join(f"{k} = :{k}" for k in updates if k != "id")
        db.execute(text(f"UPDATE task_milestones SET {set_clause} WHERE id = :id"), updates)
        db.commit()
    row = db.execute(
        text("SELECT * FROM task_milestones WHERE id = :id"), {"id": milestone_id}
    ).fetchone()
    return _row_to_dict(row)


@router.delete("/api/task-milestones/{milestone_id}", status_code=204)
def delete_milestone(milestone_id: int, db=Depends(get_db)) -> None:
    existing = db.execute(
        text("SELECT id FROM task_milestones WHERE id = :id"), {"id": milestone_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="マイルストーンが見つかりません")
    # Unlink tasks from this milestone
    db.execute(
        text("UPDATE tasks SET milestone_id = NULL WHERE milestone_id = :id"),
        {"id": milestone_id},
    )
    db.execute(
        text("DELETE FROM task_milestones WHERE id = :id"), {"id": milestone_id}
    )
    db.commit()


# ===== バルク操作 =====

@router.put("/api/tasks/bulk")
def bulk_update_tasks(req: BulkUpdateRequest, db=Depends(get_db)) -> Dict[str, Any]:
    if len(req.task_ids) > 50:
        raise HTTPException(status_code=400, detail="一度に更新できるのは50件までです")
    if not req.task_ids:
        raise HTTPException(status_code=400, detail="task_ids が空です")

    updates: Dict[str, Any] = {}
    if req.status is not None:
        updates["status"] = req.status
    if req.priority is not None:
        updates["priority"] = req.priority
    if req.assignee_id is not None:
        updates["assignee_id"] = req.assignee_id
    if req.assignee_name is not None:
        updates["assignee_name"] = req.assignee_name
    if not updates:
        raise HTTPException(status_code=400, detail="更新フィールドが指定されていません")

    updates["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    # SQLite does not support array bind; use IN with individual params
    id_params = {f"id_{i}": tid for i, tid in enumerate(req.task_ids)}
    id_placeholders = ", ".join(f":id_{i}" for i in range(len(req.task_ids)))
    params = {**updates, **id_params}
    db.execute(text(f"UPDATE tasks SET {set_clause} WHERE id IN ({id_placeholders})"), params)
    db.commit()

    # status 変更時は親タスクの progress を再計算
    if req.status is not None:
        parent_rows = db.execute(
            text(f"SELECT DISTINCT parent_id FROM tasks WHERE id IN ({id_placeholders}) AND parent_id IS NOT NULL"),
            id_params,
        ).fetchall()
        for pr in parent_rows:
            _recalc_progress(pr[0], db)

    return {"updated": len(req.task_ids)}


@router.post("/api/tasks/bulk-create", status_code=201)
def bulk_create_tasks(req: BulkCreateRequest, db=Depends(get_db)) -> List[Dict[str, Any]]:
    if len(req.tasks) > 50:
        raise HTTPException(status_code=400, detail="一度に作成できるのは50件までです")
    created = []
    now = _now_iso()
    for t in req.tasks:
        result = db.execute(
            text("""
                INSERT INTO tasks (title, description, status, priority, category_id, due_date,
                                   estimated_minutes, actual_minutes, project_name,
                                   assignee_id, assignee_name, parent_id, milestone_id, start_date,
                                   source_meeting_id, source_type,
                                   created_at, updated_at)
                VALUES (:title, :description, :status, :priority, :category_id, :due_date,
                        :estimated_minutes, :actual_minutes, :project_name,
                        :assignee_id, :assignee_name, :parent_id, :milestone_id, :start_date,
                        :source_meeting_id, :source_type,
                        :created_at, :updated_at)
            """),
            {
                "title": t.title, "description": t.description, "status": t.status,
                "priority": t.priority, "category_id": t.category_id, "due_date": t.due_date,
                "estimated_minutes": t.estimated_minutes, "actual_minutes": t.actual_minutes,
                "project_name": t.project_name,
                "assignee_id": t.assignee_id, "assignee_name": t.assignee_name,
                "parent_id": t.parent_id, "milestone_id": t.milestone_id, "start_date": t.start_date,
                "source_meeting_id": t.source_meeting_id, "source_type": t.source_type or "manual",
                "created_at": now, "updated_at": now,
            },
        )
        created.append(result.lastrowid)
    db.commit()
    # Fetch all created
    id_params = {f"id_{i}": tid for i, tid in enumerate(created)}
    id_placeholders = ", ".join(f":id_{i}" for i in range(len(created)))
    rows = db.execute(
        text(_TASK_DETAIL_SELECT + f" WHERE t.id IN ({id_placeholders})"),
        {**id_params, **_today_params()},
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ===== AI: 議事録からタスク抽出 =====

@router.post("/api/tasks/extract-from-meeting")
def extract_tasks_from_meeting(req: MeetingExtractRequest, db=Depends(get_db)) -> Dict[str, Any]:
    from gemini_client import get_client

    # Fetch meeting info
    session = db.execute(
        text("SELECT id, title, participants FROM meeting_sessions WHERE id = :id"),
        {"id": req.meeting_id},
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")
    session_dict = _row_to_dict(session)

    # Fetch transcripts
    chunks = db.execute(
        text("SELECT transcript FROM meeting_chunks WHERE session_id = :sid ORDER BY id"),
        {"sid": req.meeting_id},
    ).fetchall()
    transcript = " ".join(c[0] for c in chunks if c[0])

    if not transcript.strip():
        raise HTTPException(status_code=400, detail="議事録のテキストが空です")

    prompt = f"""以下の会議録からアクションアイテム（タスク）を抽出してJSON配列で返してください。

会議タイトル: {session_dict.get('title', '不明')}
参加者: {session_dict.get('participants', '不明')}

議事録:
{transcript[:8000]}

以下のJSON配列形式で返してください。JSONのみ返してください。
[
  {{
    "title": "タスクタイトル",
    "assignee_name": "担当者名（議事録から推定、不明ならnull）",
    "due_date": "YYYY-MM-DD（推定、不明ならnull）",
    "priority": "low|medium|high",
    "description": "詳細説明"
  }}
]
"""

    try:
        client = get_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
        )
        raw = response.text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        parsed = json.loads(raw)
    except Exception as e:
        logger.error(f"Meeting extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"AI解析エラー: {e}")

    # Validate and normalize
    proposed_tasks = []
    for item in parsed:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        proposed_tasks.append({
            "title": item.get("title", ""),
            "assignee_name": item.get("assignee_name"),
            "due_date": item.get("due_date"),
            "priority": item.get("priority", "medium"),
            "description": item.get("description"),
        })

    return {
        "meeting_id": req.meeting_id,
        "meeting_title": session_dict.get("title", ""),
        "proposed_tasks": proposed_tasks,
        "count": len(proposed_tasks),
    }


# ===== AI: レポート生成 =====

@router.post("/api/tasks/report/generate")
def generate_report(req: ReportGenerateRequest, db=Depends(get_db)) -> Dict[str, Any]:
    from gemini_client import get_client

    now = datetime.now(timezone.utc)

    # Determine date range
    if req.start_date and req.end_date:
        start = req.start_date
        end = req.end_date
    elif req.period == "weekly":
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
    elif req.period == "monthly":
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
    else:
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")

    # Query tasks
    where = ["(t.created_at >= :start OR t.updated_at >= :start)", "t.updated_at <= :end_dt"]
    params: Dict[str, Any] = {"start": f"{start}T00:00:00", "end_dt": f"{end}T23:59:59"}
    if req.project_name:
        where.append("t.project_name = :pn")
        params["pn"] = req.project_name

    tasks = db.execute(
        text(f"""
            SELECT t.title, t.status, t.priority, t.assignee_name, t.due_date, t.project_name
            FROM tasks t
            WHERE {' AND '.join(where)}
            ORDER BY t.status, t.priority
        """),
        params,
    ).fetchall()

    task_list = [_row_to_dict(r) for r in tasks]
    total = len(task_list)
    done = sum(1 for t in task_list if t.get("status") == "done")
    in_progress = sum(1 for t in task_list if t.get("status") == "in_progress")
    todo = sum(1 for t in task_list if t.get("status") == "todo")
    overdue = sum(1 for t in task_list if t.get("due_date") and t["due_date"] < end and t.get("status") != "done")
    completion_rate = int((done / total) * 100) if total > 0 else 0

    summary_data = {
        "period": f"{start} ~ {end}",
        "project_name": req.project_name or "全プロジェクト",
        "total": total,
        "done": done,
        "in_progress": in_progress,
        "todo": todo,
        "overdue": overdue,
        "completion_rate": completion_rate,
        "tasks": task_list[:50],  # limit for prompt size
    }

    prompt = f"""以下のタスク管理データに基づいて、日本語でフォーマルなPMステータスレポートをMarkdown形式で生成してください。

レポート期間: {summary_data['period']}
プロジェクト: {summary_data['project_name']}
タスク総数: {total}
完了: {done} ({completion_rate}%)
進行中: {in_progress}
未着手: {todo}
期限超過: {overdue}

タスク一覧:
{json.dumps(summary_data['tasks'], ensure_ascii=False, indent=2)[:4000]}

以下の構成でレポートを生成してください:
1. エグゼクティブサマリー
2. 進捗状況（完了率、主要な完了タスク）
3. 課題・リスク（期限超過タスク、遅延の傾向）
4. 次週のアクション計画
5. 所見

Markdownのみ返してください。"""

    try:
        client = get_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
        )
        report_md = response.text.strip()
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        raise HTTPException(status_code=500, detail=f"AI レポート生成エラー: {e}")

    return {
        "period": summary_data["period"],
        "project_name": summary_data["project_name"],
        "stats": {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "todo": todo,
            "overdue": overdue,
            "completion_rate": completion_rate,
        },
        "report_markdown": report_md,
    }


# ===== ポートフォリオ & ワークロード =====

@router.get("/api/tasks/portfolio")
def get_portfolio(db=Depends(get_db)) -> List[Dict[str, Any]]:
    """プロジェクト別のタスク集計（ポートフォリオダッシュボード用）"""
    rows = db.execute(
        text("""
            SELECT
                COALESCE(t.project_name, '未分類') AS project_name,
                COUNT(*) AS total,
                SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) AS done,
                SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
                SUM(CASE WHEN t.status = 'todo' THEN 1 ELSE 0 END) AS todo,
                SUM(CASE WHEN t.due_date IS NOT NULL AND t.due_date < date('now') AND t.status != 'done' THEN 1 ELSE 0 END) AS overdue,
                MIN(t.due_date) AS earliest_due,
                MAX(t.due_date) AS latest_due
            FROM tasks t
            GROUP BY COALESCE(t.project_name, '未分類')
            ORDER BY project_name
        """)
    ).fetchall()
    results = []
    for r in rows:
        d = _row_to_dict(r)
        total = d.get("total", 0)
        done = d.get("done", 0)
        d["completion_rate"] = int((done / total) * 100) if total > 0 else 0
        results.append(d)
    return results


@router.get("/api/tasks/workload")
def get_workload(db=Depends(get_db)) -> List[Dict[str, Any]]:
    """担当者別のタスク集計（ワークロード表示用）"""
    rows = db.execute(
        text("""
            SELECT
                COALESCE(t.assignee_name, '未割当') AS assignee_name,
                COALESCE(t.assignee_id, '') AS assignee_id,
                COUNT(*) AS total,
                SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) AS done,
                SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
                SUM(CASE WHEN t.status = 'todo' THEN 1 ELSE 0 END) AS todo,
                SUM(CASE WHEN t.due_date IS NOT NULL AND t.due_date < date('now') AND t.status != 'done' THEN 1 ELSE 0 END) AS overdue
            FROM tasks t
            GROUP BY COALESCE(t.assignee_name, '未割当'), COALESCE(t.assignee_id, '')
            ORDER BY total DESC
        """)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ===== タスク CRUD =====

@router.get("/api/tasks")
def get_tasks(
    status: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    priority: Optional[str] = Query(None),
    project_name: Optional[str] = Query(None),
    assignee_name: Optional[str] = Query(None),
    label_id: Optional[int] = Query(None),
    milestone_id: Optional[int] = Query(None),
    parent_id: Optional[int] = Query(None),
    db=Depends(get_db),
) -> List[Dict[str, Any]]:
    where = ["1=1"]
    params: Dict[str, Any] = {}
    if status:
        where.append("t.status = :status")
        params["status"] = status
    if category_id is not None:
        where.append("t.category_id = :category_id")
        params["category_id"] = category_id
    if priority:
        where.append("t.priority = :priority")
        params["priority"] = priority
    if project_name:
        where.append("t.project_name = :project_name")
        params["project_name"] = project_name
    if assignee_name:
        where.append("t.assignee_name = :assignee_name")
        params["assignee_name"] = assignee_name
    if label_id is not None:
        where.append("EXISTS (SELECT 1 FROM task_label_map tlm WHERE tlm.task_id = t.id AND tlm.label_id = :label_id)")
        params["label_id"] = label_id
    if milestone_id is not None:
        where.append("t.milestone_id = :milestone_id")
        params["milestone_id"] = milestone_id
    if parent_id is not None:
        where.append("t.parent_id = :parent_id")
        params["parent_id"] = parent_id

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    params["day_start"] = f"{today_str}T00:00:00+00:00"
    params["day_end"]   = f"{today_str}T23:59:59+00:00"

    sql = f"""
        SELECT t.*, c.name AS category_name, c.color AS category_color,
            m.name AS milestone_name,
            (SELECT GROUP_CONCAT(tl.name, ',') FROM task_label_map tlm
             JOIN task_labels tl ON tlm.label_id = tl.id
             WHERE tlm.task_id = t.id) AS label_names,
            (SELECT GROUP_CONCAT(tl.color, ',') FROM task_label_map tlm
             JOIN task_labels tl ON tlm.label_id = tl.id
             WHERE tlm.task_id = t.id) AS label_colors,
            (SELECT GROUP_CONCAT(CAST(tl.id AS TEXT), ',') FROM task_label_map tlm
             JOIN task_labels tl ON tlm.label_id = tl.id
             WHERE tlm.task_id = t.id) AS label_ids,
            CASE WHEN EXISTS (
                SELECT 1 FROM task_reminders r
                WHERE r.task_id = t.id AND r.is_sent = 0
                  AND r.remind_at >= :day_start AND r.remind_at < :day_end
            ) THEN 1 ELSE 0 END AS has_today_reminder
        FROM tasks t
        LEFT JOIN task_categories c ON t.category_id = c.id
        LEFT JOIN task_milestones m ON t.milestone_id = m.id
        WHERE {' AND '.join(where)}
        ORDER BY
            CASE t.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            t.created_at DESC
    """
    rows = db.execute(text(sql), params).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/api/tasks", status_code=201)
def create_task(req: TaskCreate, db=Depends(get_db)) -> Dict[str, Any]:
    now = _now_iso()
    # Validate parent depth if parent_id is set
    if req.parent_id:
        _check_parent_depth(req.parent_id, db)

    result = db.execute(
        text("""
            INSERT INTO tasks (title, description, status, priority, category_id, due_date,
                               estimated_minutes, actual_minutes, project_name,
                               assignee_id, assignee_name, parent_id, milestone_id, start_date,
                               source_meeting_id, source_type,
                               created_at, updated_at)
            VALUES (:title, :description, :status, :priority, :category_id, :due_date,
                    :estimated_minutes, :actual_minutes, :project_name,
                    :assignee_id, :assignee_name, :parent_id, :milestone_id, :start_date,
                    :source_meeting_id, :source_type,
                    :created_at, :updated_at)
        """),
        {
            "title": req.title,
            "description": req.description,
            "status": req.status,
            "priority": req.priority,
            "category_id": req.category_id,
            "due_date": req.due_date,
            "estimated_minutes": req.estimated_minutes,
            "actual_minutes": req.actual_minutes,
            "project_name": req.project_name,
            "assignee_id": req.assignee_id,
            "assignee_name": req.assignee_name,
            "parent_id": req.parent_id,
            "milestone_id": req.milestone_id,
            "start_date": req.start_date,
            "source_meeting_id": req.source_meeting_id,
            "source_type": req.source_type or "manual",
            "created_at": now,
            "updated_at": now,
        },
    )
    db.commit()

    # Recalc parent progress if this is a subtask
    if req.parent_id:
        _recalc_progress(req.parent_id, db)

    if req.due_date:
        _upsert_auto_reminder(result.lastrowid, req.title, req.due_date, db)
        db.commit()
    row = db.execute(
        text(_TASK_DETAIL_SELECT + " WHERE t.id = :id"),
        {"id": result.lastrowid, **_today_params()},
    ).fetchone()
    return _row_to_dict(row)


@router.get("/api/tasks/{task_id}")
def get_task(task_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    row = db.execute(
        text(_TASK_DETAIL_SELECT + " WHERE t.id = :id"),
        {"id": task_id, **_today_params()},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")

    task = _row_to_dict(row)

    comments = db.execute(
        text("SELECT * FROM task_comments WHERE task_id = :tid ORDER BY created_at ASC"),
        {"tid": task_id},
    ).fetchall()
    task["comments"] = [_row_to_dict(c) for c in comments]

    reminders = db.execute(
        text("SELECT * FROM task_reminders WHERE task_id = :tid ORDER BY remind_at ASC"),
        {"tid": task_id},
    ).fetchall()
    task["reminders"] = [_row_to_dict(r) for r in reminders]

    return task


@router.put("/api/tasks/{task_id}")
def update_task(task_id: int, req: TaskUpdate, db=Depends(get_db)) -> Dict[str, Any]:
    existing = db.execute(
        text("SELECT id FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")

    updates: Dict[str, Any] = {}
    if req.title is not None:
        updates["title"] = req.title
    if req.description is not None:
        updates["description"] = req.description
    if req.status is not None:
        updates["status"] = req.status
    if req.priority is not None:
        updates["priority"] = req.priority
    if "category_id" in req.model_fields_set:
        updates["category_id"] = req.category_id
    if "due_date" in req.model_fields_set:
        updates["due_date"] = req.due_date  # None（クリア）も含めてセット
    if "estimated_minutes" in req.model_fields_set:
        updates["estimated_minutes"] = req.estimated_minutes
    if "actual_minutes" in req.model_fields_set:
        updates["actual_minutes"] = req.actual_minutes
    if "project_name" in req.model_fields_set:
        updates["project_name"] = req.project_name
    if "assignee_id" in req.model_fields_set:
        updates["assignee_id"] = req.assignee_id
    if "assignee_name" in req.model_fields_set:
        updates["assignee_name"] = req.assignee_name
    if "parent_id" in req.model_fields_set:
        if req.parent_id is not None:
            _check_parent_depth(req.parent_id, db)
        updates["parent_id"] = req.parent_id
    if "milestone_id" in req.model_fields_set:
        updates["milestone_id"] = req.milestone_id
    if "start_date" in req.model_fields_set:
        updates["start_date"] = req.start_date

    if updates:
        updates["updated_at"] = _now_iso()
        updates["id"] = task_id
        set_clause = ", ".join(f"{k} = :{k}" for k in updates if k != "id")
        db.execute(text(f"UPDATE tasks SET {set_clause} WHERE id = :id"), updates)
        db.commit()

    # Recalc parent progress if status changed
    if req.status is not None:
        parent_row = db.execute(
            text("SELECT parent_id FROM tasks WHERE id = :id"), {"id": task_id}
        ).fetchone()
        if parent_row and parent_row[0]:
            _recalc_progress(parent_row[0], db)

    if "due_date" in req.model_fields_set:
        title_row = db.execute(
            text("SELECT title FROM tasks WHERE id = :id"), {"id": task_id}
        ).fetchone()
        task_title = title_row[0] if title_row else ""
        if req.due_date:
            _upsert_auto_reminder(task_id, task_title, req.due_date, db)
        else:
            _delete_auto_reminder(task_id, db)
        db.commit()

    row = db.execute(
        text(_TASK_DETAIL_SELECT + " WHERE t.id = :id"),
        {"id": task_id, **_today_params()},
    ).fetchone()
    return _row_to_dict(row)


def _delete_task_tree(task_id: int, db) -> None:
    """再帰的にタスクと全子孫の関連データを削除"""
    children = db.execute(
        text("SELECT id FROM tasks WHERE parent_id = :id"), {"id": task_id}
    ).fetchall()
    for child in children:
        _delete_task_tree(child[0], db)
    db.execute(text("DELETE FROM task_comments WHERE task_id = :id"), {"id": task_id})
    db.execute(text("DELETE FROM task_reminders WHERE task_id = :id"), {"id": task_id})
    db.execute(text("DELETE FROM task_label_map WHERE task_id = :id"), {"id": task_id})
    db.execute(text("DELETE FROM task_recurrence_rules WHERE source_task_id = :id"), {"id": task_id})
    db.execute(text("DELETE FROM task_dependencies WHERE predecessor_id = :id OR successor_id = :id"), {"id": task_id})
    db.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db=Depends(get_db)) -> None:
    existing = db.execute(
        text("SELECT id FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    _delete_task_tree(task_id, db)
    db.commit()


@router.post("/api/tasks/{task_id}/comments", status_code=201)
def add_comment(task_id: int, req: CommentCreate, db=Depends(get_db)) -> Dict[str, Any]:
    existing = db.execute(
        text("SELECT id FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")

    now = _now_iso()
    result = db.execute(
        text("INSERT INTO task_comments (task_id, content, created_at) VALUES (:task_id, :content, :created_at)"),
        {"task_id": task_id, "content": req.content, "created_at": now},
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM task_comments WHERE id = :id"), {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


@router.post("/api/tasks/{task_id}/reminders", status_code=201)
def add_reminder(task_id: int, req: ReminderCreate, db=Depends(get_db)) -> Dict[str, Any]:
    existing = db.execute(
        text("SELECT id FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")

    now = _now_iso()
    result = db.execute(
        text("""
            INSERT INTO task_reminders (task_id, remind_at, message, is_sent, created_at)
            VALUES (:task_id, :remind_at, :message, 0, :created_at)
        """),
        {"task_id": task_id, "remind_at": req.remind_at, "message": req.message, "created_at": now},
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM task_reminders WHERE id = :id"), {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


# ===== ラベル付与・削除 =====

@router.post("/api/tasks/{task_id}/labels", status_code=200)
def attach_labels(task_id: int, req: LabelAttach, db=Depends(get_db)) -> Dict[str, Any]:
    existing = db.execute(
        text("SELECT id FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    # Clear existing and re-attach
    db.execute(text("DELETE FROM task_label_map WHERE task_id = :tid"), {"tid": task_id})
    for lid in req.label_ids:
        db.execute(
            text("INSERT OR IGNORE INTO task_label_map (task_id, label_id) VALUES (:tid, :lid)"),
            {"tid": task_id, "lid": lid},
        )
    db.commit()
    return {"task_id": task_id, "label_ids": req.label_ids}


@router.delete("/api/tasks/{task_id}/labels/{label_id}", status_code=200)
def detach_label(task_id: int, label_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    db.execute(
        text("DELETE FROM task_label_map WHERE task_id = :tid AND label_id = :lid"),
        {"tid": task_id, "lid": label_id},
    )
    db.commit()
    return {"task_id": task_id, "removed_label_id": label_id}


# ===== サブタスク取得 =====

@router.get("/api/tasks/{task_id}/subtasks")
def get_subtasks(task_id: int, db=Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.execute(
        text(_TASK_DETAIL_SELECT + " WHERE t.parent_id = :pid ORDER BY t.sort_order, t.created_at"),
        {"pid": task_id, **_today_params()},
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ===== 繰り返しタスク =====

@router.post("/api/tasks/{task_id}/recurrence", status_code=201)
def set_recurrence(task_id: int, req: RecurrenceCreate, db=Depends(get_db)) -> Dict[str, Any]:
    existing = db.execute(
        text("SELECT id FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")

    # Remove existing rule if any
    db.execute(
        text("DELETE FROM task_recurrence_rules WHERE source_task_id = :tid"),
        {"tid": task_id},
    )

    now = datetime.now(timezone.utc)
    # Calculate next_generate based on rrule_type
    if req.rrule_type == "daily":
        next_gen = (now + timedelta(days=req.interval_value)).strftime("%Y-%m-%d")
    elif req.rrule_type == "weekly":
        next_gen = (now + timedelta(weeks=req.interval_value)).strftime("%Y-%m-%d")
    elif req.rrule_type == "biweekly":
        next_gen = (now + timedelta(weeks=2)).strftime("%Y-%m-%d")
    elif req.rrule_type == "monthly":
        next_gen = (now + timedelta(days=30 * req.interval_value)).strftime("%Y-%m-%d")
    elif req.rrule_type == "quarterly":
        next_gen = (now + timedelta(days=90)).strftime("%Y-%m-%d")
    else:
        next_gen = (now + timedelta(weeks=1)).strftime("%Y-%m-%d")

    result = db.execute(
        text("""
            INSERT INTO task_recurrence_rules
                (source_task_id, rrule_type, interval_value, day_of_week, day_of_month, next_generate, is_active, created_at)
            VALUES (:source_task_id, :rrule_type, :interval_value, :day_of_week, :day_of_month, :next_generate, 1, :created_at)
        """),
        {
            "source_task_id": task_id,
            "rrule_type": req.rrule_type,
            "interval_value": req.interval_value,
            "day_of_week": req.day_of_week,
            "day_of_month": req.day_of_month,
            "next_generate": next_gen,
            "created_at": _now_iso(),
        },
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM task_recurrence_rules WHERE id = :id"), {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


@router.delete("/api/tasks/{task_id}/recurrence", status_code=200)
def delete_recurrence(task_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    db.execute(
        text("DELETE FROM task_recurrence_rules WHERE source_task_id = :tid"),
        {"tid": task_id},
    )
    db.commit()
    return {"task_id": task_id, "recurrence": "deleted"}


# ===== 繰り返しタスク生成処理 =====

def _calc_next_generate(rrule_type: str, interval_value: int, from_date: datetime) -> str:
    """次回生成日を計算"""
    if rrule_type == "daily":
        delta = timedelta(days=interval_value)
    elif rrule_type == "weekly":
        delta = timedelta(weeks=interval_value)
    elif rrule_type == "biweekly":
        delta = timedelta(weeks=2)
    elif rrule_type == "monthly":
        delta = timedelta(days=30 * interval_value)
    elif rrule_type == "quarterly":
        delta = timedelta(days=90)
    else:
        delta = timedelta(weeks=1)
    return (from_date + delta).strftime("%Y-%m-%d")


def process_recurrences(db) -> int:
    """next_generate が今日以前の繰り返しルールを処理し、新タスクを生成する。生成数を返す。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = _now_iso()

    rules = db.execute(
        text("""
            SELECT r.*, t.title, t.description, t.priority, t.category_id,
                   t.project_name, t.assignee_id, t.assignee_name,
                   t.estimated_minutes, t.milestone_id
            FROM task_recurrence_rules r
            JOIN tasks t ON r.source_task_id = t.id
            WHERE r.is_active = 1 AND r.next_generate <= :today
        """),
        {"today": today},
    ).fetchall()

    created = 0
    for rule in rules:
        r = _row_to_dict(rule)
        # ソースタスクをコピーして新タスク作成
        new_due = r["next_generate"]  # 次回生成日を期限に設定
        result = db.execute(
            text("""
                INSERT INTO tasks (title, description, status, priority, category_id,
                                   due_date, estimated_minutes, project_name,
                                   assignee_id, assignee_name, milestone_id,
                                   source_type, created_at, updated_at)
                VALUES (:title, :description, 'todo', :priority, :category_id,
                        :due_date, :estimated_minutes, :project_name,
                        :assignee_id, :assignee_name, :milestone_id,
                        'recurrence', :created_at, :updated_at)
            """),
            {
                "title": r["title"],
                "description": r.get("description"),
                "priority": r.get("priority", "medium"),
                "category_id": r.get("category_id"),
                "due_date": new_due,
                "estimated_minutes": r.get("estimated_minutes"),
                "project_name": r.get("project_name"),
                "assignee_id": r.get("assignee_id"),
                "assignee_name": r.get("assignee_name"),
                "milestone_id": r.get("milestone_id"),
                "created_at": now_iso,
                "updated_at": now_iso,
            },
        )
        new_task_id = result.lastrowid

        # 自動リマインダー
        if new_due:
            _upsert_auto_reminder(new_task_id, r["title"], new_due, db)

        # next_generate を次回に更新
        next_gen = _calc_next_generate(
            r["rrule_type"], r.get("interval_value", 1),
            datetime.strptime(r["next_generate"], "%Y-%m-%d"),
        )
        db.execute(
            text("UPDATE task_recurrence_rules SET next_generate = :next_gen WHERE id = :id"),
            {"next_gen": next_gen, "id": r["id"]},
        )
        created += 1

    if created:
        db.commit()
    return created


@router.post("/api/tasks/recurrence/process")
def trigger_recurrence_processing(db=Depends(get_db)) -> Dict[str, Any]:
    """繰り返しタスクの手動トリガー"""
    count = process_recurrences(db)
    return {"created": count}


# ===== 依存関係 CRUD =====

_VALID_DEP_TYPES = {"FS", "FF", "SS", "SF"}


class DependencyCreate(BaseModel):
    successor_id: int
    dep_type: str = "FS"
    lag_days: int = 0


def _check_circular_dependency(task_id: int, successor_id: int, db) -> bool:
    """successor_id から辿って task_id に到達するなら循環あり"""
    visited = set()
    queue = [successor_id]
    while queue:
        current = queue.pop(0)
        if current == task_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        rows = db.execute(
            text("SELECT successor_id FROM task_dependencies WHERE predecessor_id = :id"),
            {"id": current},
        ).fetchall()
        queue.extend(r[0] for r in rows)
    return False


@router.get("/api/tasks/{task_id}/dependencies")
def get_dependencies(task_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    """タスクの先行・後続依存関係を取得"""
    predecessors = db.execute(
        text("""
            SELECT d.*, t.title AS task_title, t.status AS task_status
            FROM task_dependencies d
            JOIN tasks t ON d.predecessor_id = t.id
            WHERE d.successor_id = :tid
        """),
        {"tid": task_id},
    ).fetchall()
    successors = db.execute(
        text("""
            SELECT d.*, t.title AS task_title, t.status AS task_status
            FROM task_dependencies d
            JOIN tasks t ON d.successor_id = t.id
            WHERE d.predecessor_id = :tid
        """),
        {"tid": task_id},
    ).fetchall()
    return {
        "predecessors": [_row_to_dict(r) for r in predecessors],
        "successors": [_row_to_dict(r) for r in successors],
    }


@router.post("/api/tasks/{task_id}/dependencies", status_code=201)
def create_dependency(task_id: int, req: DependencyCreate, db=Depends(get_db)) -> Dict[str, Any]:
    """依存関係を作成（task_id が先行、req.successor_id が後続）"""
    if req.dep_type not in _VALID_DEP_TYPES:
        raise HTTPException(status_code=400, detail=f"dep_type は {_VALID_DEP_TYPES} のいずれかです")
    if task_id == req.successor_id:
        raise HTTPException(status_code=400, detail="自分自身への依存は作成できません")

    # 両方のタスクが存在するか確認
    for tid in (task_id, req.successor_id):
        row = db.execute(text("SELECT id FROM tasks WHERE id = :id"), {"id": tid}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"タスク {tid} が見つかりません")

    # 重複チェック
    existing = db.execute(
        text("SELECT id FROM task_dependencies WHERE predecessor_id = :pid AND successor_id = :sid"),
        {"pid": task_id, "sid": req.successor_id},
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="この依存関係は既に存在します")

    # 循環チェック
    if _check_circular_dependency(task_id, req.successor_id, db):
        raise HTTPException(status_code=400, detail="循環依存が検出されました")

    now = _now_iso()
    result = db.execute(
        text("""
            INSERT INTO task_dependencies (predecessor_id, successor_id, dep_type, lag_days, created_at)
            VALUES (:pid, :sid, :dep_type, :lag_days, :created_at)
        """),
        {
            "pid": task_id,
            "sid": req.successor_id,
            "dep_type": req.dep_type,
            "lag_days": req.lag_days,
            "created_at": now,
        },
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM task_dependencies WHERE id = :id"), {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


@router.delete("/api/tasks/{task_id}/dependencies/{dep_id}", status_code=200)
def delete_dependency(task_id: int, dep_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    """依存関係を削除"""
    existing = db.execute(
        text("SELECT id FROM task_dependencies WHERE id = :id AND (predecessor_id = :tid OR successor_id = :tid)"),
        {"id": dep_id, "tid": task_id},
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="依存関係が見つかりません")
    db.execute(text("DELETE FROM task_dependencies WHERE id = :id"), {"id": dep_id})
    db.commit()
    return {"deleted": dep_id}
