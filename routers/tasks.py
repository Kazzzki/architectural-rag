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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from config import GEMINI_MODEL_RAG
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Tasks"])


# ===== ヘルパー =====

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    category_id: Optional[int] = None
    due_date: Optional[str] = None
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None


class CommentCreate(BaseModel):
    content: str


class ReminderCreate(BaseModel):
    remind_at: str
    message: Optional[str] = None


class TaskChatRequest(BaseModel):
    message: str


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
        for item in result:
            db.execute(
                text("UPDATE task_reminders SET is_sent = 1 WHERE id = :id"),
                {"id": item["id"]},
            )
        db.commit()
    return result


# ===== AI チャット（/api/tasks/{id} より前に定義） =====

@router.post("/api/tasks/chat")
def task_chat(req: TaskChatRequest, db=Depends(get_db)) -> Dict[str, Any]:
    """Gemini でユーザーのテキストを解析し、タスク作成 or リマインダー設定を自動実行"""
    from gemini_client import get_client

    now = datetime.now(timezone.utc)
    JST = timezone(timedelta(hours=9))
    now_jst = now.astimezone(JST)
    today_jst       = now_jst.strftime("%Y-%m-%d")
    tomorrow_jst    = (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after_jst   = (now_jst + timedelta(days=2)).strftime("%Y-%m-%d")
    # 今週の日曜日（weekday: 月=0, 日=6）
    days_to_sunday  = (6 - now_jst.weekday()) % 7 or 7
    this_sunday_jst = (now_jst + timedelta(days=days_to_sunday)).strftime("%Y-%m-%d")
    next_monday_jst = (now_jst + timedelta(days=(7 - now_jst.weekday()))).strftime("%Y-%m-%d")

    # カテゴリ一覧を取得してプロンプトに渡す
    cats = db.execute(text("SELECT id, name FROM task_categories")).fetchall()
    cats_list = [{"id": r[0], "name": r[1]} for r in cats]

    prompt = f"""あなたはタスク管理アシスタントです。ユーザーの日本語テキストを解析して、適切なアクションを判断し、JSONのみを返してください。

ユーザーのテキスト: "{req.message}"
現在日時 (UTC ISO): {now.isoformat()}
現在日付 (JST): {today_jst}
利用可能なカテゴリ: {json.dumps(cats_list, ensure_ascii=False)}

【相対日付の変換ルール】
- 「今日」= {today_jst}
- 「明日」= {tomorrow_jst}
- 「明後日」= {day_after_jst}
- 「今週中」「今週末」= {this_sunday_jst}
- 「来週」= {next_monday_jst}
- 時刻は JST で解釈し UTC に変換（例: 10:00 JST → 01:00 UTC = 前日T01:00:00+00:00）

【優先度の判断ルール】
- 「urgent」「緊急」「急ぎ」「至急」「重要」「ASAP」「早急」などがある場合 → priority="high"
- 明示的な指定がない場合 → priority="medium"

【アクション選択ルール】
- タスク作成のみ → action="create_task"
- リマインダー設定のみ（「〇時に教えて」「リマインドして」「通知して」など）→ action="set_reminder"
- タスク作成＋リマインダー設定の両方の意図がある場合 → action="create_task_with_reminder"
- 判断が難しい場合はタスク作成を選択してください

以下のJSON形式のいずれかで返してください（他のテキストは一切不要）:

タスク作成:
{{"action": "create_task", "title": "タスクタイトル", "description": "説明（省略可）", "priority": "low|medium|high", "category_id": null, "due_date": "YYYY-MM-DD または null", "estimated_minutes": null}}

リマインダー設定:
{{"action": "set_reminder", "task_title": "タスクのタイトル", "remind_at": "YYYY-MM-DDTHH:MM:SS+00:00", "message": "リマインダーメッセージ"}}

タスク作成＋リマインダー設定:
{{"action": "create_task_with_reminder", "title": "タスクタイトル", "description": "説明（省略可）", "priority": "low|medium|high", "category_id": null, "due_date": "YYYY-MM-DD または null", "estimated_minutes": null, "remind_at": "YYYY-MM-DDTHH:MM:SS+00:00", "message": "リマインダーメッセージ"}}

JSONのみ返してください。"""

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
                INSERT INTO tasks (title, description, status, priority, category_id, due_date, estimated_minutes, created_at, updated_at)
                VALUES (:title, :description, 'todo', :priority, :category_id, :due_date, :estimated_minutes, :created_at, :updated_at)
            """),
            {
                "title": parsed.get("title", req.message[:50]),
                "description": parsed.get("description"),
                "priority": parsed.get("priority", "medium"),
                "category_id": parsed.get("category_id"),
                "due_date": parsed.get("due_date"),
                "estimated_minutes": parsed.get("estimated_minutes"),
                "created_at": now_iso,
                "updated_at": now_iso,
            },
        )
        db.commit()
        task_row = db.execute(
            text("""
                SELECT t.*, c.name AS category_name, c.color AS category_color
                FROM tasks t LEFT JOIN task_categories c ON t.category_id = c.id
                WHERE t.id = :id
            """),
            {"id": result.lastrowid},
        ).fetchone()
        title = parsed.get("title", "")
        return {"action": "create_task", "task": _row_to_dict(task_row), "message": f"タスク「{title}」を作成しました"}

    elif action in ("set_reminder", "create_reminder"):
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
        return {"action": "set_reminder", "message": f"リマインダーを設定しました: {remind_at}"}

    elif action == "create_task_with_reminder":
        # タスク作成
        result = db.execute(
            text("""
                INSERT INTO tasks (title, description, status, priority, category_id, due_date, estimated_minutes, created_at, updated_at)
                VALUES (:title, :description, 'todo', :priority, :category_id, :due_date, :estimated_minutes, :created_at, :updated_at)
            """),
            {
                "title": parsed.get("title", req.message[:50]),
                "description": parsed.get("description"),
                "priority": parsed.get("priority", "medium"),
                "category_id": parsed.get("category_id"),
                "due_date": parsed.get("due_date"),
                "estimated_minutes": parsed.get("estimated_minutes"),
                "created_at": now_iso,
                "updated_at": now_iso,
            },
        )
        db.commit()
        task_id = result.lastrowid

        # リマインダー作成
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

        task_row = db.execute(
            text("""
                SELECT t.*, c.name AS category_name, c.color AS category_color
                FROM tasks t LEFT JOIN task_categories c ON t.category_id = c.id
                WHERE t.id = :id
            """),
            {"id": task_id},
        ).fetchone()
        title = parsed.get("title", "")
        remind_at = parsed.get("remind_at", "")
        return {
            "action": "create_task_with_reminder",
            "task": _row_to_dict(task_row),
            "message": f"タスク「{title}」を作成し、リマインダーを設定しました: {remind_at}",
        }

    else:
        raise HTTPException(status_code=400, detail="テキストを解析できませんでした")


# ===== タスク CRUD =====

@router.get("/api/tasks")
def get_tasks(
    status: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    priority: Optional[str] = Query(None),
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

    sql = f"""
        SELECT t.*, c.name AS category_name, c.color AS category_color
        FROM tasks t
        LEFT JOIN task_categories c ON t.category_id = c.id
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
    result = db.execute(
        text("""
            INSERT INTO tasks (title, description, status, priority, category_id, due_date,
                               estimated_minutes, actual_minutes, created_at, updated_at)
            VALUES (:title, :description, :status, :priority, :category_id, :due_date,
                    :estimated_minutes, :actual_minutes, :created_at, :updated_at)
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
            "created_at": now,
            "updated_at": now,
        },
    )
    db.commit()
    row = db.execute(
        text("""
            SELECT t.*, c.name AS category_name, c.color AS category_color
            FROM tasks t LEFT JOIN task_categories c ON t.category_id = c.id
            WHERE t.id = :id
        """),
        {"id": result.lastrowid},
    ).fetchone()
    return _row_to_dict(row)


@router.get("/api/tasks/{task_id}")
def get_task(task_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT t.*, c.name AS category_name, c.color AS category_color
            FROM tasks t LEFT JOIN task_categories c ON t.category_id = c.id
            WHERE t.id = :id
        """),
        {"id": task_id},
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
        text("SELECT id, title, due_date FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")

    due_date_changed = "due_date" in req.model_fields_set

    updates: Dict[str, Any] = {}
    if req.title is not None:
        updates["title"] = req.title
    if req.description is not None:
        updates["description"] = req.description
    if req.status is not None:
        updates["status"] = req.status
    if req.priority is not None:
        updates["priority"] = req.priority
    if req.category_id is not None:
        updates["category_id"] = req.category_id
    if due_date_changed:
        updates["due_date"] = req.due_date or None
    if req.estimated_minutes is not None:
        updates["estimated_minutes"] = req.estimated_minutes
    if req.actual_minutes is not None:
        updates["actual_minutes"] = req.actual_minutes

    if updates:
        updates["updated_at"] = _now_iso()
        updates["id"] = task_id
        set_clause = ", ".join(f"{k} = :{k}" for k in updates if k != "id")
        db.execute(text(f"UPDATE tasks SET {set_clause} WHERE id = :id"), updates)
        db.commit()

    # due_date 変更時のリマインダー自動管理
    if due_date_changed:
        now_iso = _now_iso()
        new_due_date = req.due_date or None
        task_title = updates.get("title") or existing._mapping["title"]

        if new_due_date:
            # 当日（00:00〜23:59）の未送信リマインダーが存在しない場合のみ自動生成
            day_start = f"{new_due_date}T00:00:00"
            day_end = f"{new_due_date}T23:59:59"
            existing_reminder = db.execute(
                text("""
                    SELECT id FROM task_reminders
                    WHERE task_id = :task_id AND is_sent = 0
                      AND remind_at >= :day_start AND remind_at <= :day_end
                """),
                {"task_id": task_id, "day_start": day_start, "day_end": day_end},
            ).fetchone()
            if not existing_reminder:
                # 09:00 JST = 00:00 UTC
                remind_at_utc = f"{new_due_date}T00:00:00+00:00"
                db.execute(
                    text("""
                        INSERT INTO task_reminders (task_id, remind_at, message, is_sent, created_at)
                        VALUES (:task_id, :remind_at, :message, 0, :created_at)
                    """),
                    {
                        "task_id": task_id,
                        "remind_at": remind_at_utc,
                        "message": f"「{task_title}」の期限日です",
                        "created_at": now_iso,
                    },
                )
                db.commit()
        else:
            # due_date 削除 → 自動生成リマインダー（未送信）を削除
            db.execute(
                text("""
                    DELETE FROM task_reminders
                    WHERE task_id = :task_id AND is_sent = 0
                      AND message LIKE '「%」の期限日です'
                """),
                {"task_id": task_id},
            )
            db.commit()

    row = db.execute(
        text("""
            SELECT t.*, c.name AS category_name, c.color AS category_color
            FROM tasks t LEFT JOIN task_categories c ON t.category_id = c.id
            WHERE t.id = :id
        """),
        {"id": task_id},
    ).fetchone()
    return _row_to_dict(row)


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db=Depends(get_db)) -> None:
    existing = db.execute(
        text("SELECT id FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    db.execute(text("DELETE FROM task_comments WHERE task_id = :id"), {"id": task_id})
    db.execute(text("DELETE FROM task_reminders WHERE task_id = :id"), {"id": task_id})
    db.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})
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
