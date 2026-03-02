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

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, func, or_, text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

from config import DB_PATH, BASE_DIR

# DBファイルの保存場所 (移行用)
OLD_DB_FILE = BASE_DIR / "data" / "antigravity.db"

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

    # --- コンテキストシート ---
    context_sheet       = Column(Text,     nullable=True)  # 生成されたコンテキストシート本文
    context_sheet_role  = Column(String,   nullable=True)  # 生成時の役割 (pmcm / designer / cost)
    context_sheet_model = Column(String,   nullable=True)  # 使用したモデル名
    context_sheet_at    = Column(DateTime, nullable=True)  # 生成日時


class PersonalContext(Base):
    """パーソナルコンテキスト管理テーブル（個人知見・判断基準などを保持）"""
    __tablename__ = "personal_contexts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False)   # 'judgement' | 'lesson' | 'insight'
    content = Column(Text, nullable=False)     # 抽出された知見の要約
    trigger_keywords = Column(Text, nullable=True)                    # JSON: ["ECI", "早期選定", ...]
    project_tag = Column(String, nullable=True)                  # プロジェクト名（任意）
    source_question = Column(Text, nullable=True)                    # 元になったユーザー発言
    merge_history = Column(Text, nullable=True)                    # JSON: 過去にマージされた内容のログ
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)   # 無効化フラグ


class ContextSheet(Base):
    """複数MDファイルを結合・分析して生成したコンテキストシートの管理テーブル"""
    __tablename__ = 'context_sheets'

    id         = Column(Integer, primary_key=True, autoincrement=True)
    title      = Column(String, nullable=True)       # ユーザーが付ける任意の名前
    role       = Column(String, nullable=False)      # pmcm / designer / cost
    model      = Column(String, nullable=False)      # 使用モデル名
    file_paths = Column(Text, nullable=False)        # JSON配列: 結合元ファイルパス一覧
    char_limit = Column(Integer, default=80000)      # 使用した文字数上限
    truncated  = Column(Boolean, default=False)      # 圧縮が発生したか
    content    = Column(Text, nullable=True)         # 生成されたシート本文
    created_at = Column(DateTime, default=datetime.now)


# DB接続設定
engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 旧DBパス（データ移行用）
# iCloud同期下の旧パスを想定。新しいDBパスはDB_DIR/antigravity.db
OLD_DB_FILE = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "antigravity" / "data" / "antigravity.db"


def init_db():
    """テーブルを作成（存在しなければ）およびデータ移行"""
    # 新規パスのディレクトリ作成（config.pyでも行っているが念のため）
    db_file_path = Path(DB_PATH.replace("sqlite:///", ""))
    db_file_path.parent.mkdir(parents=True, exist_ok=True)

    # 既存のDB（iCloud同期下）があれば、新規パスへコピー（移行）
    if OLD_DB_FILE.exists() and not db_file_path.exists():
        import shutil
        try:
            logger.info(f"Migrating database from {OLD_DB_FILE} to {db_file_path}")
            shutil.copy2(OLD_DB_FILE, db_file_path)
            logger.info("Database migration successful.")
        except Exception as e:
            logger.error(f"Database migration failed: {e}")

    Base.metadata.create_all(bind=engine)
    logger.info(f"Database initialized at {db_file_path}")

    # ===== スキーママイグレーション（既存DB向け） =====
    # SQLAlchemy の create_all は既存テーブルへの列追加を行わないため、
    # 不足列を ALTER TABLE で安全に追加する。
    _run_migrations()


def _run_migrations():
    """既存テーブルへの列追加マイグレーション（べき等・エラー無視）"""
    migrations = [
        # documents テーブルへの context_sheet 列追加（前バージョンからの移行）
        "ALTER TABLE documents ADD COLUMN context_sheet TEXT",
        "ALTER TABLE documents ADD COLUMN context_sheet_role VARCHAR",
        "ALTER TABLE documents ADD COLUMN context_sheet_model VARCHAR",
        "ALTER TABLE documents ADD COLUMN context_sheet_at DATETIME",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info(f"Migration applied: {sql[:60]}")
            except Exception:
                # 列がすでに存在する場合は "duplicate column name" エラーが出るので無視
                pass


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


# ========== パーソナルコンテキスト用 CRUD ==========

def find_similar_contexts(keywords: list[str], limit: int = 5) -> list[PersonalContext]:
    """trigger_keywordsのいずれかにマッチするエントリを取得（LIKE検索）"""
    session = SessionLocal()
    try:
        query = session.query(PersonalContext).filter(PersonalContext.is_active == True)
        
        if keywords:
            conditions = [PersonalContext.trigger_keywords.like(f"%{kw}%") for kw in keywords]
            if conditions:
                query = query.filter(or_(*conditions))
            
        return query.order_by(PersonalContext.updated_at.desc()).limit(limit).all()
    finally:
        session.close()

def insert_context(entry: dict) -> PersonalContext:
    """新規エントリを挿入"""
    session = SessionLocal()
    try:
        new_ctx = PersonalContext(
            type=entry.get("type"),
            content=entry.get("content"),
            trigger_keywords=json.dumps(entry.get("trigger_keywords", []), ensure_ascii=False),
            project_tag=entry.get("project_tag"),
            source_question=entry.get("source_question"),
            merge_history=json.dumps([])
        )
        session.add(new_ctx)
        session.commit()
        session.refresh(new_ctx)
        return new_ctx
    except Exception as e:
        session.rollback()
        logger.error(f"Error inserting personal context: {e}")
        raise
    finally:
        session.close()

def merge_context(existing_id: int, new_content: str, merge_log: dict) -> None:
    """既存エントリのcontentとmerge_historyを更新"""
    session = SessionLocal()
    try:
        ctx = session.query(PersonalContext).filter(PersonalContext.id == existing_id).first()
        if ctx:
            ctx.content = new_content
            
            history = []
            if ctx.merge_history:
                try:
                    history = json.loads(ctx.merge_history)
                except json.JSONDecodeError:
                    pass
            history.append(merge_log)
            ctx.merge_history = json.dumps(history, ensure_ascii=False)
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error merging personal context: {e}")
        raise
    finally:
        session.close()

def invalidate_context(existing_id: int) -> None:
    """is_active=Falseに設定（論理削除）"""
    session = SessionLocal()
    try:
        ctx = session.query(PersonalContext).filter(PersonalContext.id == existing_id).first()
        if ctx:
            ctx.is_active = False
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error invalidating personal context: {e}")
        raise
    finally:
        session.close()


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
    db_file_path = Path(DB_PATH.replace("sqlite:///", ""))
    print(f"Database created/migrated at: {db_file_path}")

    # 既存JSONからの移行
    result = migrate_from_json()
    print(f"Migration complete: {result}")
