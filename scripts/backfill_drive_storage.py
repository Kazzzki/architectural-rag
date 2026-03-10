#!/usr/bin/env python3
import os
import sys
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# プロジェクトルートをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PDF_STORAGE_DIR, PDF_STORAGE_MODE
from database import get_session, Artifact, DocumentVersion, LegacyDocument
from drive_sync import upload_rag_pdf_to_drive, get_auth_status

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backfill():
    if PDF_STORAGE_MODE != "drive":
        logger.error("PDF_STORAGE_MODE is not set to 'drive'. Aborting.")
        return

    status = get_auth_status()
    if not status['authenticated']:
        logger.error(f"Google Drive is not authenticated: {status['message']}")
        return

    session = get_session()
    try:
        # 1. PDF_STORAGE_DIR 内のファイルをスキャン
        pdf_dir = Path(PDF_STORAGE_DIR)
        if not pdf_dir.exists():
            logger.info("PDF storage directory does not exist.")
            return

        pdf_files = list(pdf_dir.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} local PDFs to check.")

        for pdf_path in pdf_files:
            # ハッシュ取得 (ファイル名がハッシュ)
            source_pdf_hash = pdf_path.stem
            
            # ハッシュが正しいか簡易チェック (32文字以上)
            if len(source_pdf_hash) < 16:
                logger.warning(f"Skipping file with suspicious hash name: {pdf_path.name}")
                continue

            # 2. DB で Artifact を探す
            # まずは DocumentVersion を起点にする
            # Try full hash first
            version = session.query(DocumentVersion).filter(DocumentVersion.version_hash == source_pdf_hash).first()
            
            # If not found, try common truncated versions (e.g. first 8 chars or from filename)
            if not version and len(source_pdf_hash) > 16:
                short_hash = source_pdf_hash[:8]
                version = session.query(DocumentVersion).filter(DocumentVersion.version_hash.like(f"{short_hash}%")).first()

            if not version:
                logger.warning(f"No DB record found for hash {source_pdf_hash}. Skipping.")
                continue

            # Artifact レコードの有無確認
            artifact = None
            if version:
                artifact = session.query(Artifact).filter(
                    Artifact.version_id == version.id,
                    Artifact.artifact_type == "raw_file"
                ).first()

            # すでに Drive ID がある場合はスキップ
            if artifact and artifact.drive_file_id:
                logger.info(f"Skip: {source_pdf_hash[:8]} already has Drive ID: {artifact.drive_file_id}")
                continue

            # 3. アップロード実行
            logger.info(f"Backfilling {pdf_path.name} to Drive...")
            drive_id = upload_rag_pdf_to_drive(
                local_path=str(pdf_path),
                source_pdf_hash=source_pdf_hash,
                subfolder_name="pdfs"
            )

            if drive_id:
                logger.info(f"Success: {source_pdf_hash[:8]} -> {drive_id}")
                
                # Artifact レコード更新/作成
                if not artifact and version:
                    artifact = Artifact(
                        version_id=version.id,
                        artifact_type="raw_file",
                        storage_path=str(pdf_path),
                        drive_file_id=drive_id,
                        storage_type="drive",
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(artifact)
                elif artifact:
                    artifact.drive_file_id = drive_id
                    artifact.storage_type = "drive"
                
                # Legacy にもあれば Drive ID を同期
                if legacy:
                    legacy.drive_file_id = drive_id
                
                if version:
                    version.drive_status = "synced"
                
                session.commit()
            else:
                logger.error(f"Failed to upload {pdf_path.name}")

    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    backfill()
