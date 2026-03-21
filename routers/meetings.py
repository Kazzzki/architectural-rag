"""
routers/meetings.py — 会議文字起こし API

エンドポイント:
  GET    /api/meetings                  会議セッション一覧
  POST   /api/meetings                  新規セッション作成
  GET    /api/meetings/{id}             セッション詳細 + 全チャンク（文字起こし全文）
  POST   /api/meetings/chunk            音声チャンク受信 → Gemini文字起こし → DB保存
  POST   /api/meetings/{id}/finalize    全チャンクを Gemini でサマリー生成
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from google.genai import types
from pydantic import BaseModel
from sqlalchemy import text

import config
from database import get_db
from gemini_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Meetings"])


# ===== ヘルパー =====

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    return dict(row._mapping)


# ===== Pydantic モデル =====

class SessionCreate(BaseModel):
    project_name: Optional[str] = None
    title: str
    participants: Optional[str] = None  # カンマ区切りの参加者名


# ===== エンドポイント =====

@router.get("/api/meetings")
def list_meetings(db=Depends(get_db)) -> List[Dict[str, Any]]:
    """会議セッション一覧（チャンク数付き）"""
    rows = db.execute(text("""
        SELECT
            s.*,
            COUNT(c.id) AS chunk_count
        FROM meeting_sessions s
        LEFT JOIN meeting_chunks c ON c.session_id = s.id
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """)).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/api/meetings", status_code=201)
def create_meeting(req: SessionCreate, db=Depends(get_db)) -> Dict[str, Any]:
    """新規会議セッションを作成して id を返す"""
    now = _now_iso()
    result = db.execute(text("""
        INSERT INTO meeting_sessions (project_name, title, participants, created_at, updated_at)
        VALUES (:project_name, :title, :participants, :created_at, :updated_at)
    """), {
        "project_name": req.project_name,
        "title": req.title,
        "participants": req.participants,
        "created_at": now,
        "updated_at": now,
    })
    db.commit()
    row = db.execute(
        text("SELECT * FROM meeting_sessions WHERE id = :id"),
        {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


@router.get("/api/meetings/{session_id}")
def get_meeting(session_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    """セッション詳細 + 全チャンクの文字起こし"""
    session = db.execute(
        text("SELECT * FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    chunks = db.execute(text("""
        SELECT * FROM meeting_chunks
        WHERE session_id = :sid
        ORDER BY chunk_index ASC, created_at ASC
    """), {"sid": session_id}).fetchall()

    result = _row_to_dict(session)
    result["chunks"] = [_row_to_dict(c) for c in chunks]
    result["full_transcript"] = "\n\n".join(
        c["transcript"] for c in result["chunks"] if c.get("transcript")
    )
    return result


@router.post("/api/meetings/chunk", status_code=201)
async def receive_chunk(
    session_id: int = Form(...),
    chunk_index: int = Form(0),
    file: UploadFile = File(...),
    db=Depends(get_db),
) -> Dict[str, Any]:
    """音声チャンクを受け取り Gemini で文字起こして DB に保存"""
    # セッション存在確認
    session = db.execute(
        text("SELECT id FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議セッションが見つかりません")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音声データが空です")

    mime_type = file.content_type or "audio/webm"

    # Gemini 文字起こし（既存 transcribe.py と同パターン）
    try:
        client = get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL_TRANSCRIPTION,
            contents=[
                types.Part(inline_data=types.Blob(mime_type=mime_type, data=audio_bytes)),
                types.Part(text=(
                    "この音声を日本語でそのまま文字起こしてください。"
                    "句読点をつけて自然な日本語にしてください。"
                    "会議・ミーティングの音声です。"
                    "余計な説明・補足・翻訳は不要です。文字起こし結果のテキストのみ返してください。"
                )),
            ],
        )
        transcript = (response.text or "").strip()
    except Exception as e:
        logger.error(f"Gemini transcribe error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文字起こしエラー: {str(e)}")

    # DB 保存
    now = _now_iso()
    result = db.execute(text("""
        INSERT INTO meeting_chunks (session_id, chunk_index, transcript, created_at)
        VALUES (:session_id, :chunk_index, :transcript, :created_at)
    """), {
        "session_id": session_id,
        "chunk_index": chunk_index,
        "transcript": transcript,
        "created_at": now,
    })
    # セッションの updated_at を更新
    db.execute(text(
        "UPDATE meeting_sessions SET updated_at = :now WHERE id = :id"
    ), {"now": now, "id": session_id})
    db.commit()

    chunk_row = db.execute(
        text("SELECT * FROM meeting_chunks WHERE id = :id"),
        {"id": result.lastrowid}
    ).fetchone()
    return {**_row_to_dict(chunk_row), "transcript": transcript}


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    project_name: Optional[str] = None
    participants: Optional[str] = None


@router.patch("/api/meetings/{session_id}")
def update_meeting(session_id: int, req: SessionUpdate, db=Depends(get_db)) -> Dict[str, Any]:
    """会議セッションのメタデータを更新"""
    session = db.execute(
        text("SELECT id FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    updates: Dict[str, Any] = {}
    if req.title is not None:
        updates["title"] = req.title
    if req.project_name is not None:
        updates["project_name"] = req.project_name
    if req.participants is not None:
        updates["participants"] = req.participants

    if updates:
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["updated_at"] = _now_iso()
        updates["id"] = session_id
        db.execute(text(f"UPDATE meeting_sessions SET {set_clause}, updated_at = :updated_at WHERE id = :id"), updates)
        db.commit()

    row = db.execute(text("SELECT * FROM meeting_sessions WHERE id = :id"), {"id": session_id}).fetchone()
    return _row_to_dict(row)


@router.post("/api/meetings/{session_id}/finalize")
def finalize_meeting(session_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    """全チャンクの文字起こしを Gemini でサマリー生成し DB に保存"""
    session = db.execute(
        text("SELECT * FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    chunks = db.execute(text("""
        SELECT transcript FROM meeting_chunks
        WHERE session_id = :sid
        ORDER BY chunk_index ASC, created_at ASC
    """), {"sid": session_id}).fetchall()

    full_text = "\n\n".join(r[0] for r in chunks if r[0])
    if not full_text:
        summary = "（文字起こしデータなし）"
    else:
        try:
            client = get_client()
            prompt = (
                f"以下は会議の文字起こしです。\n\n{full_text}\n\n"
                "この会議の内容を日本語で簡潔にサマリーしてください。"
                "・決定事項、・アクションアイテム、・主な議論点 の3セクションで整理してください。"
            )
            response = client.models.generate_content(
                model=config.GEMINI_MODEL_RAG,
                contents=prompt,
            )
            summary = (response.text or "").strip()
        except Exception as e:
            logger.error(f"Gemini summary error: {e}", exc_info=True)
            summary = f"サマリー生成エラー: {e}"

    now = _now_iso()
    db.execute(text(
        "UPDATE meeting_sessions SET summary = :summary, updated_at = :now WHERE id = :id"
    ), {"summary": summary, "now": now, "id": session_id})
    db.commit()

    return {"session_id": session_id, "summary": summary}
