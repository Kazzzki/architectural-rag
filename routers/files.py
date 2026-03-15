from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import os
import time
import logging
import traceback

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Files & Upload"])

class DeleteFileRequest(BaseModel):
    file_path: str

class BulkDeleteRequest(BaseModel):
    file_paths: List[str]

@router.post("/api/upload/multiple")
async def upload_multiple_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """Web画面から複数ファイルを一括アップロードし、file_storeに登録する"""
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".md", ".txt"}
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    
    from config import BASE_DIR, KNOWLEDGE_BASE_DIR, UNCATEGORIZED_FOLDER
    input_dir = Path(BASE_DIR) / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    pdf_dir = Path(KNOWLEDGE_BASE_DIR) / UNCATEGORIZED_FOLDER
    pdf_dir.mkdir(parents=True, exist_ok=True)

    from metadata_repository import MetadataRepository
    repo = MetadataRepository()
    
    results = []
    errors = []
    
    for file in files:
        filename = file.filename or "unknown"
        filename = os.path.basename(filename)
        ext = os.path.splitext(filename)[1].lower()
        
        if ext not in ALLOWED_EXTENSIONS:
            errors.append({"filename": filename, "error": f"Unsupported file type: {ext}"})
            continue
            
        import re
        safe_filename = re.sub(r'[/\\:*?"<>|]', '_', filename).strip()
        if not safe_filename or safe_filename == ext or safe_filename.lstrip('.') == '':
            safe_filename = f"file_{int(time.time())}_{len(results)}{ext}"
        if not safe_filename.lower().endswith(ext):
            safe_filename = safe_filename + ext
            
        base_name = Path(safe_filename).stem
        file_path = input_dir / safe_filename
        timestamp = int(time.time())
        if file_path.exists():
            file_path = input_dir / f"{base_name}_{timestamp}_{len(results)}{ext}"
            
        try:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                errors.append({"filename": filename, "error": f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"})
                continue
                
            import hashlib
            source_pdf_hash = hashlib.sha256(content).hexdigest()
                
            content_type = "application/pdf" if ext == ".pdf" else f"image/{ext[1:]}"
            source_kind = "pdf" if ext == ".pdf" else ("image" if ext in ['.png', '.jpg', '.jpeg'] else "document")

            # Phase 2: MetadataRepositoryへの登録 (file_storeの代替)
            from metadata_repository import MetadataRepository
            repo = MetadataRepository()
            
            repo_res = repo.create_document_version(
                filename=filename,
                file_path=str(file_path),
                source_pdf_hash=source_pdf_hash,
                mime_type=content_type,
                file_size=len(content),
                source_kind=source_kind
            )
            
            file_id = repo_res["legacy_id"] # file_storeのidの代わりに一時的に利用
            version_id = repo_res["version_id"]
            
            with open(file_path, "wb") as buffer:
                buffer.write(content)

            logger.info(f"File uploaded: {file_path}, Size: {len(content)} bytes, ID: {file_id}")

            if ext in (".pdf", ".png", ".jpg", ".jpeg"):
                from pipeline_manager import process_file_pipeline
                background_tasks.add_task(process_file_pipeline, str(file_path), source_pdf_hash, version_id)
                logger.info(f"パイプライン処理をバックグラウンドタスクに登録: {file_path} (hash: {source_pdf_hash}, version: {version_id})")
            elif ext in [".md", ".txt"]:
                from config import KNOWLEDGE_BASE_DIR as _KB, UNCATEGORIZED_FOLDER as _UF
                final_md_dir = Path(_KB) / _UF
                final_md_dir.mkdir(parents=True, exist_ok=True)
                final_md_path = final_md_dir / safe_filename

                import shutil
                shutil.move(str(file_path), str(final_md_path))

                from indexer import index_file
                background_tasks.add_task(index_file, str(final_md_path))
                
            results.append({
                "filename": file_path.name,
                "status": "queued",
                "path": str(file_path),
                "file_id": file_id,
                "version_id": version_id,
                "original_name": filename,
                "source_pdf_hash": source_pdf_hash
            })
            
        except Exception as e:
            logger.error(f"Upload error for {filename}: {e}", exc_info=True)
            errors.append({"filename": filename, "error": str(e)})
            
    return {"uploaded": results, "errors": errors, "message": f"{len(results)} files uploaded successfully."}


@router.get("/api/files")
def list_files():
    """アップロード済みファイル一覧"""
    try:
        from indexer import scan_files
        files = scan_files()
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"Failed to list files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve file list")


@router.get("/api/files/view/{file_path:path}")
async def view_file(file_path: str):
    """ファイルを閲覧・ダウンロード"""
    try:
        from config import KNOWLEDGE_BASE_DIR, BASE_DIR
        kb_root = Path(KNOWLEDGE_BASE_DIR).resolve()
        target_path = (kb_root / file_path).resolve()
        
        # パストラバーサル防止: KNOWLEDGE_BASE_DIR 配下か検証
        try:
            target_path.relative_to(kb_root)
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")
           
        # KNOWLEDGE_BASE_DIR にない場合は input/ ディレクトリにフォールバック
        if not target_path.exists():
            input_path = (Path(BASE_DIR) / "input" / file_path).resolve()
            if input_path.exists():
                target_path = input_path
            else:
                raise HTTPException(status_code=404, detail="File not found")
            
        IMAGE_MIMES = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        headers = {}
        suffix = target_path.suffix.lower()
        if suffix == ".pdf":
            media_type = "application/pdf"
            from urllib.parse import quote
            safe_name = quote(target_path.name)
            headers["Content-Disposition"] = f"inline; filename*=utf-8''{safe_name}"
        elif suffix in IMAGE_MIMES:
            media_type = IMAGE_MIMES[suffix]
            from urllib.parse import quote
            safe_name = quote(target_path.name)
            headers["Content-Disposition"] = f"inline; filename*=utf-8''{safe_name}"
        elif suffix == ".md":
            media_type = "text/markdown; charset=utf-8"
        elif suffix == ".txt":
            media_type = "text/plain; charset=utf-8"
        else:
            media_type = "application/octet-stream"
            
        if headers:
            return FileResponse(target_path, media_type=media_type, headers=headers)
        else:
            return FileResponse(target_path, filename=target_path.name)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"View file error: {e}", exc_info=True)
        raise HTTPException(status_code=404, detail="File viewing failed")


@router.delete("/api/files/delete")
async def delete_file(request: DeleteFileRequest):
    """ファイルを削除（物理ファイル＋インデックス）"""
    try:
        from config import KNOWLEDGE_BASE_DIR
        target_path = Path(KNOWLEDGE_BASE_DIR) / request.file_path
        if not target_path.resolve().is_relative_to(Path(KNOWLEDGE_BASE_DIR).resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
            
        if not target_path.exists():
             raise HTTPException(status_code=404, detail="File not found")
        
        from indexer import delete_file_completely
        result = delete_file_completely(str(request.file_path))

        if result["errors"]:
            logger.warning(f"Delete completed with errors: {result['errors']}")

        return {
            "success": True,
            "deleted": result["physical_files"],
            "chroma_chunks_deleted": result["chroma_chunks"],
            "parent_chunks_deleted": result["parent_chunks"],
            "errors": result["errors"],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete file error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Delete operation failed")


@router.delete("/api/files/bulk-delete")
async def bulk_delete_files(request: BulkDeleteRequest):
    """複数ファイルを一括削除"""
    try:
        from config import KNOWLEDGE_BASE_DIR
        from indexer import delete_file_completely
        deleted_count = 0
        errors = []

        for file_path in request.file_paths:
            try:
                target_path = Path(KNOWLEDGE_BASE_DIR) / file_path
                if not target_path.resolve().is_relative_to(Path(KNOWLEDGE_BASE_DIR).resolve()):
                    errors.append(f"{file_path}: Access denied")
                    continue

                result = delete_file_completely(str(file_path))
                if result["errors"]:
                    logger.warning(f"Delete errors for {file_path}: {result['errors']}")
                deleted_count += 1

            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}", exc_info=True)
                errors.append(f"{file_path}: {str(e)}")

        status = "success" if not errors else "partial"
        return {
            "status": status,
            "message": f"{deleted_count} files deleted",
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Bulk delete error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Bulk delete operation failed")


def build_tree_recursive(current_path: Path, root_path: Path, ocr_progress_data: dict, supported_exts: set):
    """ディレクトリツリーを再帰的に構築"""
    rel_path = str(current_path.relative_to(root_path)) if current_path != root_path else ""
    node = {
        "name": current_path.name,
        "type": "directory",
        "path": rel_path,
        "children": []
    }
    
    try:
        if not current_path.exists():
            return node
            
        items = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        for item in items:
            if item.name.startswith('.') or item.name == '__pycache__' or item.name == 'chroma_db':
                continue
                
            if item.is_dir():
                node["children"].append(build_tree_recursive(item, root_path, ocr_progress_data, supported_exts))
            else:
                ext = item.suffix.lower()
                IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
                if ext not in supported_exts and ext != '.md' and ext not in IMAGE_EXTS: 
                    continue
                
                item_rel_path = str(item.relative_to(root_path))
                ocr_status = "none"
                ocr_progress = None
                
                if ext == '.pdf':
                    md_path = item.with_suffix('.md')
                    if md_path.exists():
                        ocr_status = "completed"
                elif ext in IMAGE_EXTS:
                    # 画像ファイルの場合、同名.mdがあればOCR完了
                    md_path = item.with_suffix('.md')
                    if md_path.exists():
                        ocr_status = "completed"
                
                # DB のステータス参照（PDF・画像共通）
                if item_rel_path in ocr_progress_data:
                        progress_info = ocr_progress_data[item_rel_path]
                        status = progress_info.get("status")
                        if status == "processing":
                            ocr_status = "processing"
                            ocr_progress = {
                                "current": progress_info.get("processed_pages", 0),
                                "total": progress_info.get("total_pages", 1),
                                "estimated_remaining": progress_info.get("estimated_remaining")
                            }
                        elif status == "failed":
                            ocr_status = "failed"
                            ocr_progress = {"error": progress_info.get("error")}

                node["children"].append({
                    "name": item.name,
                    "type": "file",
                    "path": item_rel_path,
                    "size": item.stat().st_size,
                    "ocr_status": ocr_status,
                    "ocr_progress": ocr_progress
                })
    except Exception as e:
        logger.error(f"Tree build error at {current_path}: {e}", exc_info=True)
        
    return node


@router.get("/api/files/tree")
def get_files_tree():
    """ファイルツリーを取得"""
    try:
        from config import KNOWLEDGE_BASE_DIR, SUPPORTED_EXTENSIONS
        # 新体系では Artifact から現在のストレージ上のパスとステータスの対応を取得
        from database import get_session, DocumentVersion, Artifact as DbArtifact
        session = get_session()
        
        # Artifact と DocumentVersion を結合して、original タイプのアーティファクトのステータスを取得
        # storage_path は絶対パスなので注意
        artifacts = session.query(DbArtifact, DocumentVersion).join(
            DocumentVersion, DbArtifact.version_id == DocumentVersion.id
        ).filter(DbArtifact.artifact_type == 'original').all()
        
        progress_data = {}
        kb_root = Path(KNOWLEDGE_BASE_DIR).resolve()
        for art, ver in artifacts:
            try:
                # storage_path を knowledge_base からの相対パスに変換
                art_path = Path(art.storage_path).resolve()
                rel_path = str(art_path.relative_to(kb_root))
                progress_data[rel_path] = {
                    "status": ver.ingest_status,
                    "processed_pages": ver.processed_pages,
                    "total_pages": ver.total_pages,
                    "error": ver.error_message
                }
            except ValueError:
                # KNOWLEDGE_BASE_DIR配下でないものはスキップ
                continue
                
        session.close()
        return build_tree_recursive(kb_root, kb_root, progress_data, SUPPORTED_EXTENSIONS)
    except Exception as e:
        logger.error(f"Failed to generate file tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="File tree generation failed")

@router.get("/api/files/{file_id}/info")
def get_file_info(file_id: str):
    """ファイル情報を取得（ステータス、パス、同期状態等）"""
    try:
        from database import get_session, DocumentVersion, Document, Upload
        session = get_session()
        # file_id = source_pdf_hash / version_hash
        version = session.query(DocumentVersion).filter(DocumentVersion.version_hash == file_id).first()
        if not version:
            session.close()
            raise HTTPException(status_code=404, detail="File not found")
        
        doc = session.query(Document).get(version.document_id)
        upload = session.query(Upload).filter(Upload.version_id == version.id).first()
        
        info = {
            "id": version.version_hash,
            "version_id": version.id,
            "status": version.ingest_status,
            "original_name": upload.original_filename if upload else doc.title,
            "created_at": version.created_at.isoformat()
        }
        session.close()
        if not info:
            raise HTTPException(status_code=404, detail="File not found")
        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve file info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="File info retrieval failed")


# ===== OCR 進捗ポーリング =====

@router.get("/api/ocr/jobs")
def get_ocr_job_by_path(file_path: str):
    """
    file_path（絶対パスまたは knowledge_base からの相対パス）で OCR 進捗を1件取得する。

    使用例:
      GET /api/ocr/jobs?file_path=uploads/sample.pdf

    レスポンス:
      {
        "file_path": "uploads/sample.pdf",
        "filename": "sample.pdf",
        "status": "processing",          # unprocessed | processing | completed | failed
        "processed_pages": 12,
        "total_pages": 50,
        "estimated_remaining": 38.5,     # 残り秒数（予測値）
        "duration": null,                # 完了時のみ設定（秒）
        "error_message": null            # failed 時のみ設定
      }

    Bug fix: Document テーブルには file_path / filename / status / processed_pages 等の
    カラムが存在しない（それらは LegacyDocument テーブルのカラム）。
    正しく LegacyDocument を参照するよう修正。
    """
    try:
        # Bug fix: Document ではなく LegacyDocument を使う
        from database import get_session, LegacyDocument

        session = get_session()
        try:
            doc = session.query(LegacyDocument).filter(
                LegacyDocument.file_path == file_path
            ).first()

            if doc is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"指定されたファイルのジョブが見つかりません: {file_path}"
                )

            return {
                "file_path": doc.file_path,
                "filename": doc.filename,
                "status": doc.status,
                "processed_pages": doc.processed_pages or 0,
                "total_pages": doc.total_pages or 0,
                "estimated_remaining": doc.estimated_remaining,
                "duration": doc.duration,
                "error_message": doc.error_message,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_ocr_job_by_path error ({file_path}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="OCR ジョブ取得に失敗しました")

