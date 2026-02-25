"""
database.py - SQLiteデータベース定義 (SQLAlchemy ORM)

ocr_progress.json と file_index.json の役割を統合したDB。
将来的にPostgreSQLへの移行も容易。
"""
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

# DBファイルの保存場所
DB_DIR = Path(__file__).parent / "data"
DB_PATH = f"sqlite:///{DB_DIR / 'antigravity.db'}"

Base = declarative_base()


class Document(Base):
    """ドキュメント管理テーブル（OCR進捗 + ファイルインデックス統合）"""
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String, unique=True)       # 相対パス (knowledge_base からの)
    file_type = Column(String)                     # pdf, md, txt, docx
    file_size = Column(Integer, default=0)         # バイト数
    category = Column(String, default="")          # フォルダ構造の第1層
    subcategory = Column(String, default="")       # フォルダ構造の第2層
    doc_type = Column(String, nullable=True)       # catalog, drawing, spec, law 등
    source_pdf_hash = Column(String, nullable=True)
    source_pdf_name = Column(String, nullable=True)

    # --- OCR/処理ステータス (旧 ocr_progress.json) ---
    status = Column(String, default="unprocessed") # unprocessed, processing, completed, failed
    total_pages = Column(Integer, default=0)
    processed_pages = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    start_time = Column(Float, nullable=True)      # time.time() 値
    end_time = Column(Float, nullable=True)
    duration = Column(Float, nullable=True)         # 秒
    estimated_remaining = Column(Float, nullable=True)

    # --- インデックス情報 (旧 file_index.json) ---
    file_hash = Column(String, nullable=True)       # ファイルハッシュ (変更検出用)
    chunk_count = Column(Integer, default=0)         # チャンク数
    last_indexed_at = Column(DateTime, nullable=True)

    # --- タイムスタンプ ---
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # --- Google Drive連携用 ---
    drive_file_id = Column(String, nullable=True)


# DB接続設定
engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """テーブルを作成（存在しなければ）"""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info(f"Database initialized at {DB_DIR / 'antigravity.db'}")


def get_db():
    """FastAPI Depends 用のDBセッションジェネレータ"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session():
    """通常のコードからDBセッションを取得"""
    return SessionLocal()


# ========== マイグレーション ==========

def migrate_from_json():
    """
    既存の ocr_progress.json と file_index.json のデータをDBに移行する。
    冪等: 既にDBにあるレコードはスキップ。
    """
    from config import KNOWLEDGE_BASE_DIR, FILE_INDEX_PATH

    init_db()
    session = SessionLocal()
    migrated_ocr = 0
    migrated_index = 0

    try:
        # --- 1. ocr_progress.json の移行 ---
        ocr_path = Path(KNOWLEDGE_BASE_DIR) / "ocr_progress.json"
        if ocr_path.exists():
            try:
                with open(ocr_path, 'r', encoding='utf-8') as f:
                    ocr_data = json.load(f)

                for rel_path, info in ocr_data.items():
                    existing = session.query(Document).filter(
                        Document.file_path == rel_path
                    ).first()

                    if existing:
                        # 既存レコードにOCR情報を追加
                        existing.status = info.get("status", "unprocessed")
                        existing.total_pages = info.get("total_pages", 0)
                        existing.processed_pages = info.get("processed_pages", 0)
                        existing.start_time = info.get("start_time")
                        existing.end_time = info.get("end_time")
                        existing.duration = info.get("duration")
                        existing.estimated_remaining = info.get("estimated_remaining")
                        existing.error_message = info.get("error")
                    else:
                        doc = Document(
                            filename=Path(rel_path).name,
                            file_path=rel_path,
                            file_type=Path(rel_path).suffix.lower().lstrip('.'),
                            status=info.get("status", "unprocessed"),
                            total_pages=info.get("total_pages", 0),
                            processed_pages=info.get("processed_pages", 0),
                            start_time=info.get("start_time"),
                            end_time=info.get("end_time"),
                            duration=info.get("duration"),
                            estimated_remaining=info.get("estimated_remaining"),
                            error_message=info.get("error"),
                        )
                        session.add(doc)
                    migrated_ocr += 1

                session.commit()

                # バックアップ
                backup = ocr_path.with_suffix('.json.bak')
                ocr_path.rename(backup)
                logger.info(f"Migrated {migrated_ocr} OCR records. Backup: {backup}")

            except Exception as e:
                session.rollback()
                logger.error(f"OCR migration error: {e}")

        # --- 2. file_index.json の移行 ---
        index_path = Path(FILE_INDEX_PATH)
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)

                for rel_path, info in index_data.get("files", {}).items():
                    existing = session.query(Document).filter(
                        Document.file_path == rel_path
                    ).first()

                    if existing:
                        existing.file_hash = info.get("hash")
                        existing.chunk_count = info.get("chunk_count", 0)
                        if info.get("indexed_at"):
                            try:
                                existing.last_indexed_at = datetime.fromisoformat(
                                    info["indexed_at"]
                                )
                            except (ValueError, TypeError):
                                pass
                    else:
                        doc = Document(
                            filename=Path(rel_path).name,
                            file_path=rel_path,
                            file_type=Path(rel_path).suffix.lower().lstrip('.'),
                            file_hash=info.get("hash"),
                            chunk_count=info.get("chunk_count", 0),
                        )
                        if info.get("indexed_at"):
                            try:
                                doc.last_indexed_at = datetime.fromisoformat(
                                    info["indexed_at"]
                                )
                            except (ValueError, TypeError):
                                pass
                        session.add(doc)
                    migrated_index += 1

                session.commit()

                # バックアップ
                backup = index_path.with_suffix('.json.bak')
                index_path.rename(backup)
                logger.info(f"Migrated {migrated_index} index records. Backup: {backup}")

            except Exception as e:
                session.rollback()
                logger.error(f"Index migration error: {e}")

    finally:
        session.close()

    return {
        "ocr_records": migrated_ocr,
        "index_records": migrated_index,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Initializing database...")
    init_db()
    print(f"Database created at: {DB_DIR / 'antigravity.db'}")

    # 既存JSONからの移行
    result = migrate_from_json()
    print(f"Migration complete: {result}")
