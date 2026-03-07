"""
database.py - SQLiteデータベース定義 (SQLAlchemy ORM)

ocr_progress.json と file_index.json の役割を統合したDB。
将来的にPostgreSQLへの移行も容易。
"""
import json
import os
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, func, or_, text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

logger = logging.getLogger(__name__)

from config import DB_PATH, BASE_DIR

Base = declarative_base()


class Document(Base):
    """
    RAGシステムの論理的な文書（例：「〇〇仕様書」という概念自体）
    """
    __tablename__ = 'documents'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    canonical_id = Column(String, nullable=True, unique=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class DocumentVersion(Base):
    """
    ドキュメントの特定の版（ファイルアップロードごとのバージョン）
    """
    __tablename__ = 'document_versions'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey('documents.id'), nullable=False)
    version_hash = Column(String, nullable=False, unique=True)  # source_pdf_hash等に相当
    ingest_status = Column(String, nullable=False, default="accepted") # accepted, ocr_processing, classified, searchable, etc.
    searchable = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    error_message = Column(Text, nullable=True)

class Upload(Base):
    """
    ユーザーからのアップロード単位
    """
    __tablename__ = 'uploads'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(String, ForeignKey('document_versions.id'), nullable=True)
    original_filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    source_kind = Column(String, nullable=False) # 'pdf', 'image', 'document'
    created_at = Column(DateTime, default=datetime.now)

class Artifact(Base):
    """
    処理過程で生成されたファイル群 (raw_pdf, ocr_markdown, page_blocks_json, chunks_jsonl)
    """
    __tablename__ = 'artifacts'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(String, ForeignKey('document_versions.id'), nullable=False)
    artifact_type = Column(String, nullable=False) # 'raw_pdf', 'ocr_markdown', 'page_blocks_json'
    storage_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

class Job(Base):
    """
    非同期処理のジョブトラッキング
    """
    __tablename__ = 'jobs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(String, ForeignKey('document_versions.id'), nullable=True)
    job_type = Column(String, nullable=False) # 'ingest', 'drive_sync', 'reindex'
    status = Column(String, nullable=False, default="queued") # queued, running, completed, failed
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

class LegacyDocument(Base):
    """旧ドキュメント管理テーブル（OCR進捗 + ファイルインデックス統合）"""
    __tablename__ = 'legacy_documents'

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


class ChatSession(Base):
    """チャットセッション管理テーブル"""
    __tablename__ = 'chat_sessions'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=True)        # 最初のユーザー発言先頭30文字から自動生成
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """チャットメッセージ管理テーブル"""
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False)
    role = Column(String, nullable=False)        # "user" または "assistant"
    content = Column(Text, nullable=False)       # 発言内容
    sources = Column(Text, nullable=True)        # JSON文字列 (参照ファイルリスト)
    model = Column(String, nullable=True)        # 使用モデル名
    created_at = Column(DateTime, default=datetime.now)

    session = relationship("ChatSession", back_populates="messages")


# ========== Layer A Memory v2 Models ==========

class MemoryItem(Base):
    __tablename__ = 'memory_items'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    memory_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    key_norm = Column(String, nullable=True)
    title = Column(String, nullable=True)
    canonical_text = Column(Text, nullable=False)
    value_json = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=True)
    entities_json = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    salience = Column(Float, nullable=False, default=0.0)
    utility_score = Column(Float, nullable=False, default=0.0)
    support_count = Column(Integer, nullable=False, default=1)
    contradiction_count = Column(Integer, nullable=False, default=0)
    first_seen_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    last_confirmed_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    supersedes_id = Column(String, nullable=True)
    source_hash = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    
    __table_args__ = (
        Index('idx_memory_items_user_type_status', 'user_id', 'memory_type', 'status'),
        Index('idx_memory_items_user_key', 'user_id', 'key_norm'),
        Index('idx_memory_items_user_last_used', 'user_id', 'last_used_at'),
    )


class MemoryEvidence(Base):
    __tablename__ = 'memory_evidence'
    
    id = Column(String, primary_key=True)
    memory_item_id = Column(String, ForeignKey('memory_items.id'), nullable=False)
    user_id = Column(String, nullable=False)
    conversation_id = Column(String, nullable=False)
    message_index_start = Column(Integer, nullable=True)
    message_index_end = Column(Integer, nullable=True)
    quote_text = Column(Text, nullable=True)
    evidence_strength = Column(Float, nullable=False, default=0.0)
    occurred_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('idx_memory_evidence_memory', 'memory_item_id'),
        Index('idx_memory_evidence_user_conversation', 'user_id', 'conversation_id'),
    )


class MemoryView(Base):
    __tablename__ = 'memory_views'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    view_name = Column(String, nullable=False)
    content_text = Column(Text, nullable=False)
    token_estimate = Column(Integer, nullable=False, default=0)
    source_version_hash = Column(String, nullable=False)
    generated_at = Column(DateTime, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'view_name', name='uq_memory_views_user_view'),
    )


class MemoryHistory(Base):
    __tablename__ = 'memory_history'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    memory_item_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    actor = Column(String, nullable=False, default='system')
    prompt_version = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('idx_memory_history_item', 'memory_item_id'),
    )


class MemoryCompactionRun(Base):
    __tablename__ = 'memory_compaction_runs'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    granularity = Column(String, nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    source_count = Column(Integer, nullable=False, default=0)
    output_memory_item_id = Column(String, nullable=True)
    status = Column(String, nullable=False)
    error_text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


class MemoryIngestionRun(Base):
    __tablename__ = 'memory_ingestion_runs'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    conversation_id = Column(String, nullable=False)
    source_hash = Column(String, nullable=False)
    status = Column(String, nullable=False)
    extracted_count = Column(Integer, nullable=False, default=0)
    saved_count = Column(Integer, nullable=False, default=0)
    error_text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'conversation_id', 'source_hash', name='uq_memory_ingestion_runs_user_conv_hash'),
    )

# ========== Layer B Scope Engine Models ==========

class Settings(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

class ProjectProfile(Base):
    __tablename__ = 'project_profiles'
    project_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    phase = Column(String, default='')
    order_type = Column(String, default='')
    client = Column(String, default='')
    objective = Column(String, default='')
    key_constraints = Column(String, default='')
    current_priority = Column(String, default='')
    current_issues = Column(String, default='')
    rag_notes = Column(String, default='')
    source_json = Column(Text, default='{}')
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('idx_project_profiles_user', 'user_id'),
    )

class ProjectView(Base):
    __tablename__ = 'project_views'
    project_id = Column(String, primary_key=True)
    user_id = Column(String, primary_key=True)
    view_name = Column(String, primary_key=True)
    content_text = Column(String, nullable=False)
    token_estimate = Column(Integer, nullable=False, default=0)
    source_version_hash = Column(String, nullable=False)
    generated_at = Column(DateTime, nullable=False, default=datetime.now)

class MemoryScopeLink(Base):
    __tablename__ = 'memory_scope_links'
    id = Column(String, primary_key=True)
    memory_item_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    scope_type = Column(String, nullable=False)
    scope_id = Column(String, nullable=False)
    relation_type = Column(String, nullable=False, default='primary')
    weight = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('idx_memory_scope_links_scope', 'user_id', 'scope_type', 'scope_id'),
        Index('idx_memory_scope_links_memory', 'memory_item_id'),
    )


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
        # context_sheets テーブルの新規作成（存在しない場合のみ）
        """CREATE TABLE IF NOT EXISTS context_sheets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      VARCHAR,
            role       VARCHAR NOT NULL,
            model      VARCHAR NOT NULL,
            file_paths TEXT    NOT NULL,
            char_limit INTEGER DEFAULT 80000,
            truncated  BOOLEAN DEFAULT 0,
            content    TEXT,
            created_at DATETIME
        )""",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info(f"Migration applied: {sql[:60]}")
            except Exception:
                # 列/テーブルが既存の場合はスキップ
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

def get_project_memories(project_tag: str, limit: int = 20) -> list[PersonalContext]:
    """特定のプロジェクトに関連するアクティブなコンテキストを取得"""
    session = SessionLocal()
    try:
        return session.query(PersonalContext).filter(
            PersonalContext.is_active == True,
            PersonalContext.project_tag == project_tag
        ).order_by(PersonalContext.updated_at.desc()).limit(limit).all()
    finally:
        session.close()

def get_global_lessons(exclude_project_tag: str = None, limit: int = 20) -> list[PersonalContext]:
    """他プロジェクトの教訓などを取得"""
    session = SessionLocal()
    try:
        query = session.query(PersonalContext).filter(
            PersonalContext.is_active == True,
            PersonalContext.type == 'lesson'
        )
        if exclude_project_tag:
            query = query.filter(PersonalContext.project_tag != exclude_project_tag)
        return query.order_by(PersonalContext.updated_at.desc()).limit(limit).all()
    finally:
        session.close()

def insert_context(entry: dict) -> PersonalContext:
    """新規エントリを挿入"""
    session = SessionLocal()
    try:
        project_tag = entry.get("project_id") or entry.get("project_tag")
        new_ctx = PersonalContext(
            type=entry.get("type"),
            content=entry.get("content"),
            trigger_keywords=json.dumps(entry.get("trigger_keywords", []), ensure_ascii=False),
            project_tag=project_tag,
            source_question=entry.get("source_question"),
            merge_history=json.dumps([])
        )
        session.add(new_ctx)
        session.commit()
        session.refresh(new_ctx)
        
        # Dual-write to MemoryScopeLink if project_id is available
        if project_tag:
            link = MemoryScopeLink(
                id=str(uuid.uuid4()),
                memory_item_id=f"pc_{new_ctx.id}", # mark as legacy PC
                user_id="mock_user",
                scope_type="project",
                scope_id=project_tag,
                relation_type="primary",
                weight=1.0
            )
            session.add(link)
            session.commit()
            
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
