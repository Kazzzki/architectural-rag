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
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# 文字起こしプロンプト（ハルシネーション防止付き）
TRANSCRIPTION_PROMPT = (
    "この音声を日本語でそのまま文字起こしてください。"
    "句読点をつけて自然な日本語にしてください。"
    "会議・ミーティングの音声です。"
    "余計な説明・補足・翻訳は不要です。文字起こし結果のテキストのみ返してください。"
    "音声が無音・聞き取れない・不明瞭な場合は空文字を返してください。内容を推測・創作しないでください。"
    "実際に聞こえた発話のみを書き起こしてください。"
)


def _get_dict_hint(session_id: int, db) -> str:
    """セッションに紐づくカスタム辞書をプロンプト用ヒントとして取得"""
    try:
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
            return "\n以下の専門用語が使われる可能性があります:\n" + "\n".join(terms) + "\n"
    except Exception:
        pass
    return ""


def _transcribe_segment(audio_bytes: bytes, mime_type: str, dict_hint: str = "") -> str:
    """音声バイト列をGeminiで文字起こし（temperature=0, ハルシネーション防止）"""
    client = get_client()
    response = client.models.generate_content(
        model=config.GEMINI_MODEL_TRANSCRIPTION,
        contents=[
            types.Part(inline_data=types.Blob(mime_type=mime_type, data=audio_bytes)),
            types.Part(text=TRANSCRIPTION_PROMPT + dict_hint),
        ],
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return (response.text or "").strip()


def _split_audio(audio_bytes: bytes, segment_sec: int = 600) -> List[Tuple[bytes, str]]:
    """ffmpegで音声をセグメント分割（Gemini 20MB制限対応）"""
    segments: List[Tuple[bytes, str]] = []
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as src:
        src.write(audio_bytes)
        src_path = src.name

    try:
        # ffprobeで長さ取得
        duration = segment_sec  # フォールバック
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", src_path],
                capture_output=True, text=True, timeout=30,
            )
            if probe.returncode == 0:
                import json
                info = json.loads(probe.stdout)
                duration = float(info.get("format", {}).get("duration", segment_sec))
        except Exception:
            pass

        start = 0.0
        idx = 0
        while start < duration:
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", src_path,
                     "-ss", str(start), "-t", str(segment_sec),
                     "-c", "copy", tmp_path],
                    capture_output=True, timeout=120,
                )
                if result.returncode == 0:
                    seg_bytes = Path(tmp_path).read_bytes()
                    if seg_bytes:
                        segments.append((seg_bytes, "audio/webm"))
            except Exception as e:
                logger.error(f"ffmpeg segment split error at {start}s: {e}")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            start += segment_sec
            idx += 1
    finally:
        if os.path.exists(src_path):
            os.unlink(src_path)

    return segments if segments else [(audio_bytes, "audio/webm")]


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


@router.get("/api/meetings/decisions")
def get_past_decisions(
    project_name: Optional[str] = None,
    limit: int = 50,
    db=Depends(get_db),
) -> List[Dict[str, Any]]:
    """プロジェクト横断の過去決定事項一覧"""
    where = ["n.note_type = 'decision'"]
    params: Dict[str, Any] = {"limit": limit}
    if project_name:
        where.append("s.project_name = :project_name")
        params["project_name"] = project_name
    rows = db.execute(
        text(f"""
            SELECT n.id, n.content, n.timestamp_sec, n.created_at,
                   s.id AS session_id, s.title AS meeting_title,
                   s.project_name, s.created_at AS meeting_date
            FROM meeting_live_notes n
            JOIN meeting_sessions s ON n.session_id = s.id
            WHERE {' AND '.join(where)}
            ORDER BY n.created_at DESC
            LIMIT :limit
        """),
        params,
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


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
    dict_hint = _get_dict_hint(session_id, db)

    # Gemini 文字起こし（temperature=0, ハルシネーション防止プロンプト）
    try:
        transcript = _transcribe_segment(audio_bytes, mime_type, dict_hint)
        if not transcript:
            logger.warning(f"Gemini returned empty transcript for session {session_id} chunk {chunk_index}")
            transcript = "[音声を認識できませんでした]"
    except Exception as e:
        logger.error(f"Gemini transcribe error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文字起こしエラー: {str(e)}")

    # DB 保存（リトライ時の重複防止: 既存チャンクがあれば更新）
    now = _now_iso()
    existing = db.execute(text("""
        SELECT id FROM meeting_chunks WHERE session_id = :sid AND chunk_index = :idx
    """), {"sid": session_id, "idx": chunk_index}).fetchone()

    if existing:
        chunk_id = dict(existing._mapping)["id"]
        db.execute(text("""
            UPDATE meeting_chunks SET transcript = :transcript, start_offset_sec = :start_offset_sec
            WHERE id = :id
        """), {"transcript": transcript, "start_offset_sec": start_offset_sec, "id": chunk_id})
    else:
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

    row_id = chunk_id if existing else result.lastrowid
    chunk_row = db.execute(
        text("SELECT * FROM meeting_chunks WHERE id = :id"),
        {"id": row_id}
    ).fetchone()
    return {**_row_to_dict(chunk_row), "transcript": transcript}


@router.post("/api/meetings/{session_id}/transcribe-full")
async def transcribe_full_audio(
    session_id: int,
    file: UploadFile = File(...),
    db=Depends(get_db),
) -> Dict[str, Any]:
    """録音停止後に全音声を一括でGemini文字起こし（チャンク分割はバックエンドで実行）"""
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
    dict_hint = _get_dict_hint(session_id, db)

    # 20MB超の場合はffmpegでセグメント分割
    if len(audio_bytes) > 20 * 1024 * 1024:
        segments = _split_audio(audio_bytes, segment_sec=600)
    else:
        segments = [(audio_bytes, mime_type)]

    # 既存チャンクを削除（再実行対応）
    db.execute(text("DELETE FROM meeting_chunks WHERE session_id = :sid"), {"sid": session_id})

    now = _now_iso()
    transcripts: List[str] = []
    for i, (seg_bytes, seg_mime) in enumerate(segments):
        try:
            transcript = _transcribe_segment(seg_bytes, seg_mime, dict_hint)
        except Exception as e:
            logger.error(f"Gemini transcribe error for segment {i}: {e}", exc_info=True)
            transcript = "[文字起こしエラー]"

        if not transcript:
            transcript = "[音声を認識できませんでした]"

        transcripts.append(transcript)
        db.execute(text("""
            INSERT INTO meeting_chunks (session_id, chunk_index, transcript, start_offset_sec, created_at)
            VALUES (:session_id, :chunk_index, :transcript, :start_offset_sec, :created_at)
        """), {
            "session_id": session_id,
            "chunk_index": i,
            "transcript": transcript,
            "start_offset_sec": i * 600,
            "created_at": now,
        })

    db.execute(text(
        "UPDATE meeting_sessions SET updated_at = :now WHERE id = :id"
    ), {"now": now, "id": session_id})
    db.commit()

    full_text = "\n\n".join(t for t in transcripts if t and not t.startswith("["))
    return {"session_id": session_id, "transcript": full_text, "chunk_count": len(transcripts)}


@router.post("/api/meetings/transcribe", status_code=201)
async def transcribe_and_create_session(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
    db=Depends(get_db),
) -> Dict[str, Any]:
    """音声ファイルからセッション作成→文字起こし→DB保存を一気通貫で実行。

    MeetingRecorder / MeetingUploader が呼ぶワンショットエンドポイント。
    返り値: {"id": session_id, "transcript": full_text, "chunk_count": N}
    """
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音声データが空です")

    mime_type = file.content_type or "audio/webm"
    now = _now_iso()

    # ファイル名からタイトルを生成（フォールバック）
    session_title = title or (file.filename or "").replace(".webm", "").replace("_", " ") or f"会議録音 {now[:10]}"

    # 1. セッション作成
    result = db.execute(text("""
        INSERT INTO meeting_sessions (project_name, title, participants, created_at, updated_at)
        VALUES (:project_name, :title, :participants, :created_at, :updated_at)
    """), {
        "project_name": project_name,
        "title": session_title,
        "participants": None,
        "created_at": now,
        "updated_at": now,
    })
    db.commit()
    session_id = result.lastrowid

    # 2. 音声ファイルを保存
    audio_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "audio")
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, f"{session_id}.webm")
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)
    db.execute(text(
        "UPDATE meeting_sessions SET audio_file_path = :path WHERE id = :id"
    ), {"path": audio_path, "id": session_id})

    # 3. 文字起こし（大きいファイルはセグメント分割）
    dict_hint = _get_dict_hint(session_id, db)
    if len(audio_bytes) > 20 * 1024 * 1024:
        segments = _split_audio(audio_bytes, segment_sec=600)
    else:
        segments = [(audio_bytes, mime_type)]

    transcripts: List[str] = []
    for i, (seg_bytes, seg_mime) in enumerate(segments):
        try:
            transcript = _transcribe_segment(seg_bytes, seg_mime, dict_hint)
        except Exception as e:
            logger.error(f"Gemini transcribe error for segment {i}: {e}", exc_info=True)
            transcript = "[文字起こしエラー]"
        if not transcript:
            transcript = "[音声を認識できませんでした]"

        transcripts.append(transcript)
        db.execute(text("""
            INSERT INTO meeting_chunks (session_id, chunk_index, transcript, start_offset_sec, created_at)
            VALUES (:session_id, :chunk_index, :transcript, :start_offset_sec, :created_at)
        """), {
            "session_id": session_id,
            "chunk_index": i,
            "transcript": transcript,
            "start_offset_sec": i * 600,
            "created_at": now,
        })

    db.execute(text(
        "UPDATE meeting_sessions SET updated_at = :now WHERE id = :id"
    ), {"now": _now_iso(), "id": session_id})
    db.commit()

    full_text = "\n\n".join(t for t in transcripts if t and not t.startswith("["))
    return {"id": session_id, "transcript": full_text, "chunk_count": len(transcripts)}


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    project_name: Optional[str] = None
    participants: Optional[str] = None
    notes: Optional[str] = None
    summary: Optional[str] = None
    series_name: Optional[str] = None


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
    if req.summary is not None:
        updates["summary"] = req.summary
    if req.series_name is not None:
        updates["series_name"] = req.series_name

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
                config=types.GenerateContentConfig(temperature=0.2),
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


MAX_AUDIO_SIZE = 100 * 1024 * 1024  # 100MB


@router.post("/api/meetings/{session_id}/upload-audio", status_code=200)
async def upload_audio(
    session_id: int,
    file: UploadFile = File(...),
    db=Depends(get_db),
) -> Dict[str, Any]:
    """録音した音声ファイルをアップロードして保存"""
    session = db.execute(
        text("SELECT id FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議セッションが見つかりません")

    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="音声ファイルが100MBを超えています")
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音声データが空です")

    audio_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "audio")
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, f"{session_id}.webm")

    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    db.execute(text(
        "UPDATE meeting_sessions SET audio_file_path = :path, updated_at = :now WHERE id = :id"
    ), {"path": audio_path, "now": _now_iso(), "id": session_id})
    db.commit()

    return {"session_id": session_id, "audio_file_path": audio_path, "size_bytes": len(audio_bytes)}


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


# ===== Phase 2: タスク統合 + テンプレート =====

@router.post("/api/meetings/{session_id}/create-tasks")
def create_tasks_from_meeting(session_id: int, db=Depends(get_db)) -> Dict[str, Any]:
    """議事録のアクションアイテムからタスクを自動作成"""
    session = db.execute(
        text("SELECT id FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    tasks = meeting_ai.create_tasks_from_meeting(session_id, db)
    return {"session_id": session_id, "tasks_created": tasks, "count": len(tasks)}


@router.get("/api/meetings/{session_id}/carry-forward")
def get_carry_forward(session_id: int, db=Depends(get_db)) -> List[Dict[str, Any]]:
    """同シリーズの未完了タスクを取得（キャリーフォワード）"""
    session = db.execute(
        text("SELECT series_name FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="会議が見つかりません")

    series_name = dict(session._mapping).get("series_name")
    return meeting_ai.get_carry_forward_tasks(series_name or "", session_id, db)


class SeriesTemplateRequest(BaseModel):
    series_name: str
    agenda_template: str = ""
    summary_prompt: str = ""


@router.get("/api/meetings/templates/{series_name}")
def get_series_template(series_name: str, db=Depends(get_db)) -> Dict[str, Any]:
    """シリーズテンプレート取得"""
    tpl = meeting_ai.get_series_template(series_name, db)
    if not tpl:
        return {"series_name": series_name, "agenda_template": "", "summary_prompt": ""}
    return tpl


@router.put("/api/meetings/templates")
def save_series_template(req: SeriesTemplateRequest, db=Depends(get_db)) -> Dict[str, Any]:
    """シリーズテンプレート保存"""
    return meeting_ai.save_series_template(req.series_name, req.agenda_template, req.summary_prompt, db)


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

    # ライブメモ取得（分類出力で使用）
    live_notes = db.execute(text("""
        SELECT timestamp_sec, content, note_type FROM meeting_live_notes
        WHERE session_id = :sid
        ORDER BY timestamp_sec ASC, id ASC
    """), {"sid": session_id}).fetchall()

    # サマリーを先頭に（Notion貼り付け時にまず概要が見える）
    if s.get("summary"):
        lines.append("## AI サマリー")
        lines.append("")
        lines.append(s["summary"])
        lines.append("")

    # ライブメモを分類して出力（決定/アクション/リスク/メモ）
    if live_notes:
        categorized: Dict[str, list] = {"decision": [], "action": [], "risk": [], "memo": []}
        for row in live_notes:
            n = _row_to_dict(row)
            ts = _format_offset(n.get("timestamp_sec"))
            prefix = f"[{ts}] " if ts else ""
            nt = n.get("note_type", "memo")
            categorized.setdefault(nt, []).append(f"{prefix}{n['content']}")

        if categorized.get("decision"):
            lines.append("## 決定事項")
            lines.append("")
            for item in categorized["decision"]:
                lines.append(f"- {item}")
            lines.append("")

        if categorized.get("action"):
            lines.append("## アクションアイテム")
            lines.append("")
            for item in categorized["action"]:
                lines.append(f"- [ ] {item}")
            lines.append("")

        if categorized.get("risk"):
            lines.append("## リスク・懸念")
            lines.append("")
            for item in categorized["risk"]:
                lines.append(f"- ⚠ {item}")
            lines.append("")

        if categorized.get("memo"):
            lines.append("## メモ")
            lines.append("")
            for item in categorized["memo"]:
                lines.append(f"- {item}")
            lines.append("")

    md = "\n".join(lines)
    # ファイル名にASCII外の文字がある場合はRFC 5987形式でエンコード
    title_safe = s.get('title', 'meeting').encode('ascii', 'replace').decode('ascii')
    filename = f"{title_safe}_{session_id}.md"
    from urllib.parse import quote
    filename_utf8 = f"{s.get('title', 'meeting')}_{session_id}.md"
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename_utf8)}"},
    )


# ===== 過去決定事項 =====

