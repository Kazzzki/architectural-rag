"""
ファイル管理ストア（SQLite）
アップロードされたファイルの論理ID・物理パス・ステータスを一元管理する。
PDFプレビュー、Google Drive同期、RAGインデキシングが全てIDベースでパスを解決する。
"""
import hashlib
import sqlite3
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "files.db"


@contextmanager
def get_db():
    """DB接続コンテキストマネージャ"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """テーブル作成"""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                current_path TEXT NOT NULL,
                content_type TEXT DEFAULT 'application/octet-stream',
                size_bytes INTEGER DEFAULT 0,
                uploaded_at TEXT NOT NULL,
                ocr_status TEXT DEFAULT 'pending',
                classification TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                drive_file_id TEXT,
                drive_synced_at TEXT,
                checksum TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_files_checksum ON files(checksum)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_files_ocr_status ON files(ocr_status)
        """)
    logger.info("Files DB initialized")


def register_file(
    original_name: str,
    current_path: str,
    content: bytes,
    content_type: str = "application/pdf"
) -> Dict[str, Any]:
    """
    ファイルを登録する。
    同一チェックサムのファイルが既存の場合はそのIDを返す。
    """
    checksum = hashlib.sha256(content).hexdigest()
    file_id = checksum[:16]
    
    with get_db() as conn:
        # 既存チェック
        existing = conn.execute(
            "SELECT id, original_name, current_path FROM files WHERE checksum = ?",
            (checksum,)
        ).fetchone()
        
        if existing:
            return {
                "id": existing["id"],
                "original_name": existing["original_name"],
                "current_path": existing["current_path"],
                "is_duplicate": True
            }
        
        conn.execute("""
            INSERT INTO files (id, original_name, current_path, content_type, 
                             size_bytes, uploaded_at, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            original_name,
            current_path,
            content_type,
            len(content),
            datetime.now().isoformat(),
            checksum
        ))
        
    return {
        "id": file_id,
        "original_name": original_name,
        "current_path": current_path,
        "is_duplicate": False
    }


def get_file(file_id: str) -> Optional[Dict[str, Any]]:
    """IDからファイル情報を取得"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        
        if not row:
            return None
        return dict(row)


def update_path(file_id: str, new_path: str) -> bool:
    """物理パスを更新（分類後のファイル移動で使用）"""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE files SET current_path = ? WHERE id = ?",
            (new_path, file_id)
        )
        return cursor.rowcount > 0


def update_ocr_status(file_id: str, status: str) -> bool:
    """OCRステータスを更新（pending / processing / completed / failed）"""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE files SET ocr_status = ? WHERE id = ?",
            (status, file_id)
        )
        return cursor.rowcount > 0


def update_classification(file_id: str, classification: str, tags: str = "[]") -> bool:
    """分類結果を更新"""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE files SET classification = ?, tags = ? WHERE id = ?",
            (classification, tags, file_id)
        )
        return cursor.rowcount > 0


def update_drive_sync(file_id: str, drive_file_id: str) -> bool:
    """Google Drive同期情報を更新"""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE files SET drive_file_id = ?, drive_synced_at = ? WHERE id = ?",
            (drive_file_id, datetime.now().isoformat(), file_id)
        )
        return cursor.rowcount > 0


def list_files(
    ocr_status: Optional[str] = None,
    unsynced_only: bool = False
) -> List[Dict[str, Any]]:
    """ファイル一覧を取得"""
    query = "SELECT * FROM files"
    conditions = []
    params = []
    
    if ocr_status:
        conditions.append("ocr_status = ?")
        params.append(ocr_status)
    
    if unsynced_only:
        conditions.append("drive_file_id IS NULL")
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY uploaded_at DESC"
    
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_file_by_checksum(checksum: str) -> Optional[Dict[str, Any]]:
    """チェックサムからファイル検索"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE checksum = ?", (checksum,)
        ).fetchone()
        return dict(row) if row else None


def get_sync_stats() -> Dict[str, Any]:
    """同期統計情報"""
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM files").fetchone()["c"]
        synced = conn.execute(
            "SELECT COUNT(*) as c FROM files WHERE drive_file_id IS NOT NULL"
        ).fetchone()["c"]
        last_sync = conn.execute(
            "SELECT MAX(drive_synced_at) as t FROM files"
        ).fetchone()["t"]
        
        return {
            "total_files": total,
            "synced_files": synced,
            "unsynced_files": total - synced,
            "last_synced_at": last_sync
        }


# 起動時にDB初期化
init_db()
