"""
routers/meetings.py — 会議文字起こし API

エンドポイント:
  GET    /api/meetings                  会議セッション一覧
  POST   /api/meetings                  新規セッション作成
  GET    /api/meetings/{id}             セッション詳細 + 全チャンク（文字起こし全文）
  POST   /api/meetings/chunk            音声チャンク受信 → Gemini文字起こし → DB保存
  POST   /api/meetings/{id}/finalize    全チャンクを Gemini でサマリー生成
  POST   /api/meetings/{id}/extract-links  エンティティ自動リンク抽出
  POST   /api/meetings/{id}/auto-tag       タグ自動付与
  GET    /api/meetings/{id}/tags           タグ一覧
  GET    /api/meetings/{id}/entity-links   エンティティリンク一覧
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
    start_offset_sec: int = Form(0),
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

    # M4: カスタム辞書をプロンプトに注入
    dict_hint = ""
    try:
        # セッションのプロジェクトから辞書を取得
        sess = db.execute(
            text("SELECT project_id FROM meeting_sessions WHERE id = :id"),
            {"id": session_id}
        ).fetchone()
        pid = dict(sess._mapping).get("project_id") if sess else None
        if pid:
            dict_rows = db.execute(text("""
                SELECT term, reading, category FROM custom_dictionary
                WHERE project_id = :pid OR project_id IS NULL LIMIT 30
            """), {"pid": pid}).fetchall()
        else:
            dict_rows = db.execute(text("""
                SELECT term, reading, category FROM custom_dictionary
                WHERE project_id IS NULL LIMIT 20
            """)).fetchall()
        if dict_rows:
            terms = []
            for r in dict_rows:
                d = dict(r._mapping)
                t = d["term"]
                if d.get("reading"):
                    t += f"（{d['reading']}）"
                terms.append(f"- {t}")
            dict_hint = "\n以下の専門用語が使われる可能性があります:\n" + "\n".join(terms) + "\n"
    except Exception:
        pass

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
                    + dict_hint
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
        INSERT INTO meeting_chunks (session_id, chunk_index, transcript, start_offset_sec, created_at)
        VALUES (:session_id, :chunk_index, :transcript, :start_offset_sec, :created_at)
    """), {
        "session_id": session_id,
        "chunk_index": chunk_index,
        "transcript": transcript,
        "start_offset_sec": start_offset_sec,
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
    notes: Optional[str] = None


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
    if req.notes is not None:
        updates["notes"] = req.notes

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

    # Phase 1B: finalize 後に自動エンティティリンク + タグ付与
    # Phase 1C P4: 自動プロジェクト分類
    try:
        import meeting_ai as _mai
        _mai.extract_entity_links(session_id, db)
        _mai.auto_tag_meeting(session_id, db)
        _mai.auto_classify_project(session_id, db)
    except Exception as e:
        logger.warning(f"Post-finalize AI extraction failed (non-blocking): {e}")

    return {"session_id": session_id, "summary": summary}


# ===== チャンクメモ =====

class ChunkNoteUpdate(BaseModel):
    note: str


@router.patch("/api/meetings/chunks/{chunk_id}/note")
def update_chunk_note(chunk_id: int, req: ChunkNoteUpdate, db=Depends(get_db)) -> Dict[str, Any]:
    """チャンク単位のメモを更新"""
    chunk = db.execute(
        text("SELECT id FROM meeting_chunks WHERE id = :id"),
        {"id": chunk_id}
    ).fetchone()
    if not chunk:
        raise HTTPException(status_code=404, detail="チャンクが見つかりません")

    try:
        db.execute(
            text("UPDATE meeting_chunks SET note = :note WHERE id = :id"),
            {"note": req.note, "id": chunk_id}
        )
        db.commit()
    except Exception as e:
        logger.error(f"Chunk note update error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存エラー: {str(e)}")

    return {"chunk_id": chunk_id, "note": req.note}


# ===== ライブメモ (Phase 1A) =====

ALLOWED_NOTE_TYPES = {"memo", "decision", "action", "risk"}


class LiveNoteCreate(BaseModel):
    session_id: int
    timestamp_sec: int
    content: str
    note_type: str = "memo"


class LiveNoteUpdate(BaseModel):
    content: Optional[str] = None
    note_type: Optional[str] = None


@router.post("/api/meetings/live-notes", status_code=201)
def create_live_note(req: LiveNoteCreate, db=Depends(get_db)) -> Dict[str, Any]:
    """ライブメモを作成（録音中にタイムスタンプ付きで追加）"""
    session = db.execute(
        text("SELECT id FROM meeting_sessions WHERE id = :id"),
        {"id": req.session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議セッションが見つかりません")

    note_type = req.note_type if req.note_type in ALLOWED_NOTE_TYPES else "memo"
    now = _now_iso()
    result = db.execute(text("""
        INSERT INTO meeting_live_notes (session_id, timestamp_sec, content, note_type, created_at)
        VALUES (:session_id, :timestamp_sec, :content, :note_type, :created_at)
    """), {
        "session_id": req.session_id,
        "timestamp_sec": req.timestamp_sec,
        "content": req.content,
        "note_type": note_type,
        "created_at": now,
    })
    db.commit()
    row = db.execute(
        text("SELECT * FROM meeting_live_notes WHERE id = :id"),
        {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


@router.get("/api/meetings/{session_id}/live-notes")
def get_live_notes(session_id: int, db=Depends(get_db)) -> List[Dict[str, Any]]:
    """セッションのライブメモ一覧（タイムスタンプ昇順）"""
    rows = db.execute(text("""
        SELECT * FROM meeting_live_notes
        WHERE session_id = :sid
        ORDER BY timestamp_sec ASC, id ASC
    """), {"sid": session_id}).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.patch("/api/meetings/live-notes/{note_id}")
def update_live_note(note_id: int, req: LiveNoteUpdate, db=Depends(get_db)) -> Dict[str, Any]:
    """ライブメモの内容・タイプを更新"""
    note = db.execute(
        text("SELECT id FROM meeting_live_notes WHERE id = :id"),
        {"id": note_id}
    ).fetchone()
    if not note:
        raise HTTPException(status_code=404, detail="メモが見つかりません")

    updates: Dict[str, Any] = {}
    if req.content is not None:
        updates["content"] = req.content
    if req.note_type is not None:
        if req.note_type in ALLOWED_NOTE_TYPES:
            updates["note_type"] = req.note_type

    if updates:
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["id"] = note_id
        db.execute(text(f"UPDATE meeting_live_notes SET {set_clause} WHERE id = :id"), updates)
        db.commit()

    row = db.execute(
        text("SELECT * FROM meeting_live_notes WHERE id = :id"),
        {"id": note_id}
    ).fetchone()
    return _row_to_dict(row)


@router.delete("/api/meetings/live-notes/{note_id}")
def delete_live_note(note_id: int, db=Depends(get_db)) -> Dict[str, str]:
    """ライブメモを削除"""
    note = db.execute(
        text("SELECT id FROM meeting_live_notes WHERE id = :id"),
        {"id": note_id}
    ).fetchone()
    if not note:
        raise HTTPException(status_code=404, detail="メモが見つかりません")

    db.execute(text("DELETE FROM meeting_live_notes WHERE id = :id"), {"id": note_id})
    db.commit()
    return {"status": "deleted"}


@router.get("/api/meetings/{session_id}/timeline")
def get_meeting_timeline(session_id: int, db=Depends(get_db)) -> List[Dict[str, Any]]:
    """チャンク（文字起こし）とライブメモを時間軸で統合して返す"""
    chunks = db.execute(text("""
        SELECT id, chunk_index, transcript, start_offset_sec, note, created_at
        FROM meeting_chunks
        WHERE session_id = :sid
        ORDER BY chunk_index ASC
    """), {"sid": session_id}).fetchall()

    notes = db.execute(text("""
        SELECT id, timestamp_sec, content, note_type, created_at
        FROM meeting_live_notes
        WHERE session_id = :sid
        ORDER BY timestamp_sec ASC
    """), {"sid": session_id}).fetchall()

    timeline = []
    for c in chunks:
        cd = _row_to_dict(c)
        timeline.append({
            "type": "chunk",
            "timestamp_sec": cd.get("start_offset_sec") or 0,
            "id": cd["id"],
            "chunk_index": cd["chunk_index"],
            "transcript": cd.get("transcript", ""),
            "note": cd.get("note"),
            "created_at": cd["created_at"],
        })
    for n in notes:
        nd = _row_to_dict(n)
        timeline.append({
            "type": "live_note",
            "timestamp_sec": nd["timestamp_sec"],
            "id": nd["id"],
            "content": nd["content"],
            "note_type": nd["note_type"],
            "created_at": nd["created_at"],
        })

    timeline.sort(key=lambda x: (x["timestamp_sec"], 0 if x["type"] == "chunk" else 1))
    return timeline


# ===== AI エンティティリンク + タグ (Phase 1B) =====

import meeting_ai


@router.post("/api/meetings/{session_id}/extract-links")
def extract_links(session_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    """文字起こし + メモからエンティティを自動検出してリンク"""
    session = db.execute(
        text("SELECT id FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    links = meeting_ai.extract_entity_links(session_id, db)
    return {"session_id": session_id, "links": links, "count": len(links)}


@router.post("/api/meetings/{session_id}/auto-tag")
def auto_tag(session_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    """文字起こしからタグを自動付与"""
    session = db.execute(
        text("SELECT id FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    tags = meeting_ai.auto_tag_meeting(session_id, db)
    return {"session_id": session_id, "tags": tags, "count": len(tags)}


@router.get("/api/meetings/{session_id}/tags")
def get_tags(session_id: int, db=Depends(get_db)) -> List[Dict[str, Any]]:
    """セッションのタグ一覧"""
    return meeting_ai.get_meeting_tags(session_id, db)


@router.get("/api/meetings/{session_id}/entity-links")
def get_entity_links(session_id: int, db=Depends(get_db)) -> List[Dict[str, Any]]:
    """セッションのエンティティリンク一覧"""
    return meeting_ai.get_entity_links(session_id, db)


@router.post("/api/meetings/{session_id}/add-tag")
def add_tag(session_id: int, tag_name: str, db=Depends(get_db)) -> Dict[str, Any]:
    """手動タグ追加"""
    result = meeting_ai.add_manual_tag(session_id, tag_name, db)
    if not result:
        raise HTTPException(status_code=400, detail="タグの追加に失敗しました")
    return result


# ===== M1: クロスミーティングRAG =====

class MeetingAskRequest(BaseModel):
    question: str
    project_name: Optional[str] = None


@router.post("/api/meetings/ask")
def ask_meetings(req: MeetingAskRequest, db=Depends(get_db)) -> Dict[str, Any]:
    """全会議横断で質問 → ソース付き回答"""
    return meeting_ai.ask_across_meetings(req.question, req.project_name, db)


# ===== M4: カスタム辞書 =====

class DictionaryEntry(BaseModel):
    project_id: Optional[str] = None
    term: str
    reading: Optional[str] = None
    category: Optional[str] = None


@router.get("/api/dictionary")
def list_dictionary(project_id: Optional[str] = None, db=Depends(get_db)) -> List[Dict[str, Any]]:
    """カスタム辞書一覧"""
    if project_id:
        rows = db.execute(text("""
            SELECT * FROM custom_dictionary
            WHERE project_id = :pid OR project_id IS NULL
            ORDER BY term
        """), {"pid": project_id}).fetchall()
    else:
        rows = db.execute(text("SELECT * FROM custom_dictionary ORDER BY term")).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/api/dictionary", status_code=201)
def add_dictionary_entry(req: DictionaryEntry, db=Depends(get_db)) -> Dict[str, Any]:
    """辞書エントリ追加"""
    now = _now_iso()
    result = db.execute(text("""
        INSERT INTO custom_dictionary (project_id, term, reading, category, created_at)
        VALUES (:pid, :term, :reading, :cat, :ca)
    """), {
        "pid": req.project_id,
        "term": req.term,
        "reading": req.reading,
        "cat": req.category,
        "ca": now,
    })
    db.commit()
    row = db.execute(
        text("SELECT * FROM custom_dictionary WHERE id = :id"),
        {"id": result.lastrowid}
    ).fetchone()
    return _row_to_dict(row)


@router.delete("/api/dictionary/{entry_id}")
def delete_dictionary_entry(entry_id: int, db=Depends(get_db)) -> Dict[str, str]:
    """辞書エントリ削除"""
    db.execute(text("DELETE FROM custom_dictionary WHERE id = :id"), {"id": entry_id})
    db.commit()
    return {"status": "deleted"}


# ===== M8: 音声ストリーミング =====

import os
from fastapi.responses import FileResponse


@router.get("/api/meetings/{session_id}/audio")
def stream_audio(session_id: int, db=Depends(get_db)):
    """音声ファイルをストリーミング返却"""
    session = db.execute(
        text("SELECT audio_file_path FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    audio_path = dict(session._mapping).get("audio_file_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="音声ファイルが見つかりません")

    return FileResponse(
        path=audio_path,
        media_type="audio/webm",
        filename=os.path.basename(audio_path),
    )


# ===== P5: シリーズ名一覧 =====

@router.get("/api/meetings/series")
def list_series(db=Depends(get_db)) -> List[str]:
    """使用中のシリーズ名一覧"""
    rows = db.execute(text("""
        SELECT DISTINCT series_name FROM meeting_sessions
        WHERE series_name IS NOT NULL AND series_name != ''
        ORDER BY series_name
    """)).fetchall()
    return [r[0] for r in rows]


# ===== 会議検索 (FTS5) =====

import re

def _sanitize_fts_query(q: str) -> str:
    """FTS5 クエリをサニタイズ: 英数字・日本語・空白のみ残しフレーズ検索"""
    cleaned = re.sub(r'[^\w\s\u3000-\u9fff\uff00-\uffef]', '', q).strip()
    if not cleaned:
        return ''
    return f'"{cleaned}"'


@router.get("/api/meetings/search")
def search_meetings(q: str = "", db=Depends(get_db)) -> List[Dict[str, Any]]:
    """会議をFTS5全文検索（空クエリは全件返却）"""
    if not q.strip():
        return list_meetings(db)

    safe_q = _sanitize_fts_query(q)
    if not safe_q:
        return list_meetings(db)

    try:
        rows = db.execute(text("""
            SELECT s.*, COUNT(c.id) AS chunk_count
            FROM meeting_fts f
            JOIN meeting_sessions s ON s.id = CAST(f.session_id AS INTEGER)
            LEFT JOIN meeting_chunks c ON c.session_id = s.id
            WHERE meeting_fts MATCH :q
            GROUP BY s.id
            ORDER BY s.updated_at DESC
        """), {"q": safe_q}).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"FTS5 search error (falling back to full list): {e}")
        return list_meetings(db)


# ===== Markdownエクスポート =====

from fastapi.responses import PlainTextResponse


def _format_offset(sec: Optional[int]) -> str:
    if sec is None or sec < 0:
        return ""
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


@router.get("/api/meetings/{session_id}/export")
def export_meeting(session_id: int, db=Depends(get_db)):
    """会議をMarkdown形式でエクスポート"""
    session = db.execute(
        text("SELECT * FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    s = _row_to_dict(session)
    chunks = db.execute(text("""
        SELECT * FROM meeting_chunks
        WHERE session_id = :sid
        ORDER BY chunk_index ASC, created_at ASC
    """), {"sid": session_id}).fetchall()

    lines = [f"# {s.get('title', '無題')}"]
    lines.append("")
    if s.get("created_at"):
        lines.append(f"- 日時: {s['created_at']}")
    if s.get("project_name"):
        lines.append(f"- プロジェクト: {s['project_name']}")
    if s.get("participants"):
        lines.append(f"- 参加者: {s['participants']}")
    lines.append("")

    if s.get("notes"):
        lines.append("## メモ")
        lines.append("")
        lines.append(s["notes"])
        lines.append("")

    if chunks:
        lines.append("## 文字起こし")
        lines.append("")
        for i, row in enumerate(chunks):
            c = _row_to_dict(row)
            ts = _format_offset(c.get("start_offset_sec"))
            header = f"### チャンク {c.get('chunk_index', i) + 1}"
            if ts:
                header += f" ({ts})"
            lines.append(header)
            lines.append("")
            if c.get("transcript"):
                lines.append(c["transcript"])
                lines.append("")
            if c.get("note"):
                lines.append(f"> メモ: {c['note']}")
                lines.append("")

    if s.get("summary"):
        lines.append("## AI サマリー")
        lines.append("")
        lines.append(s["summary"])
        lines.append("")

    md = "\n".join(lines)
    filename = f"{s.get('title', 'meeting')}_{session_id}.md"
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
