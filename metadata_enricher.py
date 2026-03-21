import os
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from classifier import DocumentClassifier
from metadata_repository import MetadataRepository
from config import KNOWLEDGE_BASE_DIR, UNCATEGORIZED_FOLDER, ENABLE_AUTO_CATEGORIZE, PDF_STORAGE_DIR, PDF_STORAGE_MODE

logger = logging.getLogger(__name__)

class MetadataEnricher:
    """
    Phase 3: 文書の正規化と分類処理を独立モジュール化。
    OCRで抽出された純粋なマークダウンに対して、
    事前定義されたルールに基づく自動分類とフロントマター付与を行う。
    """
    def __init__(self):
        self.classifier = DocumentClassifier()
        self.repo = MetadataRepository()

    def process(self, version_id: str, markdown_path: str, filepath: str, source_pdf_hash: str) -> tuple[str, str]:
        """
        1. Markdownを読み込む
        2. LLMベースの分類器(DocumentClassifier)で分類・タグ付け
        3. YAML Frontmatterを生成してMarkdown先頭に付与
        4. 最終的な配置先(KNOWLEDGE_BASE_DIR 内)へ移動
        5. 原本PDFをPDF_STORAGE_DIRへ移動
        6. DBのステータス更新・成果物(Artifact)記録
        """
        try:
            with open(markdown_path, 'r', encoding='utf-8') as f:
                markdown_text = f.read()

            filename = Path(filepath).name
            meta_input = {'title': Path(filename).stem}
            
            # マークダウンの先頭5000文字を使って分類
            classification_result = self.classifier.classify(markdown_text[:5000], meta_input)

            # --- 保存先決定 ---
            try:
                original_category = Path(filepath).parent.resolve().relative_to(Path(KNOWLEDGE_BASE_DIR).resolve())
                is_uploads = str(original_category) in ('uploads', '.', UNCATEGORIZED_FOLDER)
            except ValueError:
                original_category = UNCATEGORIZED_FOLDER
                is_uploads = True

            category_path = str(original_category)

            if not is_uploads:
                category_path = str(original_category)
            elif not ENABLE_AUTO_CATEGORIZE:
                category_path = UNCATEGORIZED_FOLDER
            else:
                primary_cat = classification_result.get('primary_category')
                if primary_cat and primary_cat not in ("uploads", UNCATEGORIZED_FOLDER):
                    category_path = primary_cat
                else:
                    category_path = UNCATEGORIZED_FOLDER

            target_md_dir = Path(KNOWLEDGE_BASE_DIR) / category_path
            target_md_dir.mkdir(parents=True, exist_ok=True)
            
            # --- Frontmatter生成とファイル書き出し ---
            # 旧実装互換のため drive_file_id などを空で渡す
            extra_meta = {
                "source_pdf_hash": source_pdf_hash,
                "pdf_filename": filename,
                "drive_file_id": "",
                "version_id": version_id,
                "modality": "text",
            }
            frontmatter = self.classifier.generate_frontmatter(classification_result, extra_meta)
            full_md_text = frontmatter + markdown_text
            
            final_md_path = target_md_dir / Path(markdown_path).name

            # 新ファイルパスに書き込み、元のOCRマークダウンは削除または上書き
            if final_md_path.resolve() != Path(markdown_path).resolve():
                with open(final_md_path, 'w', encoding='utf-8') as f:
                    f.write(full_md_text)
                os.remove(markdown_path)
            else:
                with open(final_md_path, 'w', encoding='utf-8') as f:
                    f.write(full_md_text)

            logger.info(f"[MetadataEnricher] Classified as {category_path}, saved MD to {final_md_path}")
            self.repo.save_artifact(version_id, "ocr_markdown", str(final_md_path))

            # --- 原本PDFの移動 ---
            target_pdf_dir = Path(PDF_STORAGE_DIR)
            target_pdf_dir.mkdir(parents=True, exist_ok=True)
            new_pdf_path = target_pdf_dir / f"{source_pdf_hash}{Path(filepath).suffix}"
            
            drive_file_id = None
            if new_pdf_path.resolve() != Path(filepath).resolve():
                if new_pdf_path.exists():
                    new_pdf_path.unlink()
                if Path(filepath).exists():
                    shutil.move(str(filepath), str(new_pdf_path))
                    logger.info(f"[MetadataEnricher] Moved source PDF to {new_pdf_path}")
                else:
                    logger.warning(f"[MetadataEnricher] Original file {filepath} not found for moving.")
            
            # --- Google Driveへアップロード (Phase 4) ---
            if PDF_STORAGE_MODE == "drive" and new_pdf_path.exists():
                try:
                    from drive_sync import upload_rag_pdf_to_drive
                    self.repo.update_ingest_stage_by_version_id(version_id, "uploading_to_drive")
                    
                    drive_file_id = upload_rag_pdf_to_drive(
                        local_path=str(new_pdf_path),
                        source_pdf_hash=source_pdf_hash
                    )
                    
                    if drive_file_id:
                        logger.info(f"[MetadataEnricher] Successfully uploaded to Drive: {drive_file_id}")
                        self.repo.update_ingest_stage_by_version_id(version_id, "drive_synced")
                except Exception as e:
                    # Bug fix: Drive アップロード失敗時にエラーメッセージをDBに記録する。
                    # パイプラインは続行するが、credentials.json 未配置などのエラーを
                    # ユーザーが確認できるよう error_message に残す。
                    drive_error_msg = f"Drive upload failed (pipeline continues): {e}"
                    logger.warning(f"[MetadataEnricher] {drive_error_msg}")
                    try:
                        session_db = __import__('database', fromlist=['get_session', 'DocumentVersion']).get_session()
                        try:
                            from database import DocumentVersion
                            dv = session_db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
                            if dv:
                                dv.error_message = drive_error_msg
                                dv.updated_at = datetime.now(timezone.utc)
                                session_db.commit()
                        finally:
                            session_db.close()
                    except Exception:
                        pass  # DB 記録失敗してもパイプラインは継続

            # Artifactとして記録
            self.repo.save_artifact(
                version_id=version_id, 
                artifact_type="raw_file", 
                storage_path=str(new_pdf_path),
                drive_file_id=drive_file_id,
                storage_type="drive" if drive_file_id else "local"
            )

            # Legacyのファイルパスも更新
            try:
                import file_store as fs
                file_rec = fs.get_file_by_path(filepath)
                if file_rec:
                    fs.update_path(file_rec["id"], str(new_pdf_path))
            except Exception as _e:
                pass

            # DB更新
            self.repo.update_ingest_stage_by_version_id(version_id, "enriched")

            return str(final_md_path), str(new_pdf_path)

        except Exception as e:
            logger.error(f"[MetadataEnricher] Failed for version_id={version_id}: {e}", exc_info=True)
            self.repo.update_ingest_stage_by_version_id(version_id, "enrichment_failed")
            self.repo.update_ingest_stage(filepath, "failed")
            raise e
