import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import logging

from database import get_session, LegacyDocument, Document, DocumentVersion, Upload, Artifact, Job

logger = logging.getLogger(__name__)

class MetadataRepository:
    """
    統一メタデータリポジトリ (Phase 2)
    file_store / status_manager を統合し、Single Source of Truth として単一DB操作を提供する。
    新モデル(Document, DocumentVersion, Upload 等)と旧モデル(LegacyDocument)への二重書き込みを
    行い、スムーズな移行をサポートする。
    """
    
    def create_document_version(
        self, 
        filename: str, 
        file_path: str, 
        source_pdf_hash: str,
        mime_type: str = "application/pdf",
        file_size: int = 0,
        source_kind: str = "pdf"
    ) -> Dict[str, str]:
        """
        アップロード時にレコードを生成/更新し、version_id と 旧ID (legacy_id) を返す。
        同一ハッシュ（同一ファイル）の再アップロードや同一パスへの上書きに対応するため
        INSERT ではなく upsert（既存なら更新）を使用する。
        """
        session = get_session()
        try:
            # --- 1. 旧モデル (LegacyDocument) の upsert ---
            # file_path が同じ既存レコードを探す
            doc_legacy = session.query(LegacyDocument).filter(
                LegacyDocument.file_path == file_path
            ).first()
            if not doc_legacy:
                doc_legacy = LegacyDocument(
                    filename=filename,
                    file_path=file_path,
                    source_pdf_hash=source_pdf_hash,
                    file_size=file_size,
                    file_type=filename.split('.')[-1].lower() if '.' in filename else '',
                    status="accepted",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                session.add(doc_legacy)
            else:
                doc_legacy.filename = filename
                doc_legacy.source_pdf_hash = source_pdf_hash
                doc_legacy.file_size = file_size
                doc_legacy.status = "accepted"
                doc_legacy.error_message = None
                doc_legacy.updated_at = datetime.now(timezone.utc)
            
            session.flush()  # ID取得のためflush

            # --- 2. 新モデル (Document, DocumentVersion, Upload) の upsert ---
            base_title = filename.rsplit('.', 1)[0]

            # Document: タイトルで既存を探す（なければ作成）
            doc_new = session.query(Document).filter(Document.title == base_title).first()
            if not doc_new:
                doc_new = Document(
                    title=base_title,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                session.add(doc_new)
                session.flush()

            # DocumentVersion: version_hash (= sha256) が UNIQUE なので
            # 同じハッシュが既存なら更新、なければ作成する
            doc_version = session.query(DocumentVersion).filter(
                DocumentVersion.version_hash == source_pdf_hash
            ).first()
            if doc_version:
                # 再アップロード: ステータスをリセットして再処理
                doc_version.ingest_status = "accepted"
                doc_version.searchable = False
                doc_version.error_message = None
                doc_version.updated_at = datetime.now(timezone.utc)
            else:
                doc_version = DocumentVersion(
                    document_id=doc_new.id,
                    version_hash=source_pdf_hash,
                    ingest_status="accepted",
                    searchable=False,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                session.add(doc_version)
            session.flush()

            # Upload: 同一 version_id の upload が既存でも重複追加する（アップロード履歴として残す）
            upload = Upload(
                version_id=doc_version.id,
                original_filename=filename,
                mime_type=mime_type,
                file_size=file_size,
                source_kind=source_kind,
                created_at=datetime.now(timezone.utc)
            )
            session.add(upload)

            session.commit()
            return {
                "version_id": doc_version.id,
                "document_id": doc_new.id,
                "upload_id": upload.id,
                "legacy_id": str(doc_legacy.id)
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create document version: {e}", exc_info=True)
            raise e
        finally:
            session.close()

    def save_artifact(self, version_id: str, artifact_type: str, storage_path: str, drive_file_id: Optional[str] = None, storage_type: str = "local") -> str:
        """
        Phase 3: 中間生成物 (Markdown, JSON等) の保存パスを記録する。
        Phase 4: Drive ID と ストレージ種別を追加。
        """
        session = get_session()
        try:
            artifact = Artifact(
                version_id=version_id,
                artifact_type=artifact_type,
                storage_path=storage_path,
                drive_file_id=drive_file_id,
                storage_type=storage_type,
                created_at=datetime.now(timezone.utc)
            )
            session.add(artifact)
            session.commit()
            return artifact.id
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save artifact: {e}")
            raise e
        finally:
            session.close()

    def update_ingest_stage_by_version_id(self, version_id: str, status: str) -> None:
        """
        Phase 3: 新モデルベースでのステータス更新
        """
        session = get_session()
        try:
            doc_ver = session.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
            if doc_ver:
                doc_ver.ingest_status = status
                doc_ver.updated_at = datetime.now(timezone.utc)
                session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_ingest_stage(self, filepath: str, next_stage: str, total_pages: int = 0) -> None:
        """
        OCR等の進行中ステータスを更新する (Legacy互換用)
        """
        session = get_session()
        try:
            doc = session.query(LegacyDocument).filter(LegacyDocument.file_path == filepath).first()
            if doc:
                doc.status = next_stage
                if total_pages > 0:
                    doc.total_pages = total_pages
                doc.updated_at = datetime.now(timezone.utc)
                session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_processed_pages(self, filepath: str, processed_pages: int) -> None:
        """
        OCRの進捗ページ数を更新する
        """
        session = get_session()
        try:
            doc = session.query(LegacyDocument).filter(LegacyDocument.file_path == filepath).first()
            if doc:
                doc.processed_pages = processed_pages
                doc.updated_at = datetime.now(timezone.utc)
                session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def mark_as_searchable(self, filepath: str) -> None:
        """
        Index構築が完全に成功した場合のみ呼び出され、searchable (completed) にする。
        """
        session = get_session()
        try:
            doc = session.query(LegacyDocument).filter(LegacyDocument.file_path == filepath).first()
            if doc:
                doc.status = "completed"
                doc.last_indexed_at = datetime.now(timezone.utc)
                doc.updated_at = datetime.now(timezone.utc)
                
                # 新モデルのStatusもSearchableにできればする
                doc_ver = session.query(DocumentVersion).filter(DocumentVersion.version_hash == doc.source_pdf_hash).first()
                if doc_ver:
                    doc_ver.searchable = True
                    doc_ver.ingest_status = "searchable"
                    doc_ver.updated_at = datetime.now(timezone.utc)
                
                session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def fail_processing(self, filepath: str, error_msg: str) -> None:
        """
        処理失敗時のステータス更新
        """
        session = get_session()
        try:
            doc = session.query(LegacyDocument).filter(LegacyDocument.file_path == filepath).first()
            if doc:
                doc.status = "failed"
                doc.error_message = error_msg
                doc.updated_at = datetime.now(timezone.utc)
                
                # 新モデルのErrorも更新
                doc_ver = session.query(DocumentVersion).filter(DocumentVersion.version_hash == doc.source_pdf_hash).first()
                if doc_ver:
                    doc_ver.ingest_status = "failed"
                    doc_ver.error_message = error_msg
                    doc_ver.updated_at = datetime.now(timezone.utc)
                
                session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_document_status(self, filepath: str) -> Optional[Dict[str, Any]]:
        """
        ドキュメントのステータスを取得
        """
        session = get_session()
        try:
            doc = session.query(LegacyDocument).filter(LegacyDocument.file_path == filepath).first()
            if doc:
                return {
                    "status": doc.status,
                    "pages": doc.total_pages,
                    "processed_pages": doc.processed_pages,
                    "error": doc.error_message,
                    "hash": doc.source_pdf_hash,
                    "indexed_at": doc.last_indexed_at.isoformat() if doc.last_indexed_at else None
                }
            return None
        finally:
            session.close()
