"""
status_manager.py - OCR処理ステータス管理 (SQLAlchemy版)

旧: ocr_progress.json + fcntl ファイルロック
新: SQLite DB (database.py の Document テーブル)
"""
import time
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class OCRStatusManager:
    def __init__(self, status_file: str = "ocr_progress.json"):
        """
        後方互換のため status_file 引数は受け取るが無視する。
        全データは SQLite DB に保存される。
        """
        from database import get_session
        self._get_session = get_session

    def start_processing(self, file_path: str, total_pages: int):
        """処理開始を記録"""
        from database import Document
        session = self._get_session()
        try:
            rel_path = self._get_rel_path(file_path)
            doc = session.query(Document).filter(
                Document.file_path == rel_path
            ).first()

            if not doc:
                doc = Document(
                    filename=Path(file_path).name,
                    file_path=rel_path,
                    file_type=Path(file_path).suffix.lower().lstrip('.'),
                )
                session.add(doc)

            doc.status = "processing"
            doc.total_pages = total_pages
            doc.processed_pages = 0
            doc.start_time = time.time()
            doc.end_time = None
            doc.duration = None
            doc.estimated_remaining = None
            doc.error_message = None
            doc.updated_at = datetime.now()
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"start_processing error: {e}")
        finally:
            session.close()

    def update_progress(self, file_path: str, processed_count: int):
        """進捗更新"""
        from database import Document
        session = self._get_session()
        try:
            rel_path = self._get_rel_path(file_path)
            doc = session.query(Document).filter(
                Document.file_path == rel_path
            ).first()

            if doc and doc.start_time:
                doc.processed_pages = processed_count
                doc.updated_at = datetime.now()

                # 残り時間予測
                elapsed = time.time() - doc.start_time
                if processed_count > 0:
                    avg_time_per_page = elapsed / processed_count
                    remaining_pages = doc.total_pages - processed_count
                    doc.estimated_remaining = round(avg_time_per_page * remaining_pages, 1)

                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"update_progress error: {e}")
        finally:
            session.close()

    def complete_processing(self, file_path: str):
        """処理完了"""
        from database import Document
        session = self._get_session()
        try:
            rel_path = self._get_rel_path(file_path)
            doc = session.query(Document).filter(
                Document.file_path == rel_path
            ).first()

            if doc:
                doc.status = "completed"
                doc.processed_pages = doc.total_pages
                doc.end_time = time.time()
                if doc.start_time:
                    doc.duration = round(doc.end_time - doc.start_time, 1)
                doc.estimated_remaining = 0
                doc.updated_at = datetime.now()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"complete_processing error: {e}")
        finally:
            session.close()

    def fail_processing(self, file_path: str, error: str):
        """エラー記録"""
        from database import Document
        session = self._get_session()
        try:
            rel_path = self._get_rel_path(file_path)
            doc = session.query(Document).filter(
                Document.file_path == rel_path
            ).first()

            if doc:
                doc.status = "failed"
                doc.error_message = str(error)
                doc.end_time = time.time()
                doc.updated_at = datetime.now()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"fail_processing error: {e}")
        finally:
            session.close()

    def remove_status(self, file_path: str):
        """ステータス削除"""
        from database import Document
        session = self._get_session()
        try:
            rel_path = self._get_rel_path(file_path)
            doc = session.query(Document).filter(
                Document.file_path == rel_path
            ).first()

            if doc:
                # レコードを削除するのではなくステータスをリセット
                doc.status = "unprocessed"
                doc.total_pages = 0
                doc.processed_pages = 0
                doc.start_time = None
                doc.end_time = None
                doc.duration = None
                doc.estimated_remaining = None
                doc.error_message = None
                doc.updated_at = datetime.now()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"remove_status error: {e}")
        finally:
            session.close()

    def rename_status(self, old_path: str, new_path: str):
        """ステータスの移動（リネーム）"""
        from database import Document
        session = self._get_session()
        try:
            old_rel = self._get_rel_path(old_path)
            new_rel = self._get_rel_path(new_path)
            doc = session.query(Document).filter(
                Document.file_path == old_rel
            ).first()

            if doc:
                doc.file_path = new_rel
                doc.filename = Path(new_path).name
                doc.updated_at = datetime.now()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"rename_status error: {e}")
        finally:
            session.close()

    def get_progress(self, file_path: str) -> Optional[Dict[str, Any]]:
        """特定ファイルの進捗を取得（旧JSON形式互換の辞書を返す）"""
        from database import Document
        session = self._get_session()
        try:
            rel_path = self._get_rel_path(file_path)
            doc = session.query(Document).filter(
                Document.file_path == rel_path
            ).first()

            if not doc or doc.status == "unprocessed":
                return None

            return self._doc_to_dict(doc)
        finally:
            session.close()

    def get_all_status(self) -> Dict[str, Any]:
        """全ファイルのステータスを取得（旧JSON形式互換）"""
        from database import Document
        session = self._get_session()
        try:
            docs = session.query(Document).filter(
                Document.status != "unprocessed"
            ).all()

            result = {}
            for doc in docs:
                result[doc.file_path] = self._doc_to_dict(doc)
            return result
        finally:
            session.close()

    def _doc_to_dict(self, doc) -> Dict[str, Any]:
        """Document レコードを旧JSON形式の辞書に変換"""
        d = {
            "status": doc.status,
            "total_pages": doc.total_pages or 0,
            "processed_pages": doc.processed_pages or 0,
            "start_time": doc.start_time,
            "last_updated": doc.start_time,  # 後方互換
            "estimated_remaining": doc.estimated_remaining,
        }
        if doc.end_time:
            d["end_time"] = doc.end_time
        if doc.duration:
            d["duration"] = doc.duration
        if doc.error_message:
            d["error"] = doc.error_message
        return d

    def _get_rel_path(self, file_path: str) -> str:
        from config import KNOWLEDGE_BASE_DIR
        try:
            return str(Path(file_path).relative_to(KNOWLEDGE_BASE_DIR))
        except ValueError:
            return Path(file_path).name
