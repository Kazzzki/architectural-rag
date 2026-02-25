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

    import file_store
    
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
                
            content_type = "application/pdf" if ext == ".pdf" else f"image/{ext[1:]}"
            reg = file_store.register_file(
                original_name=filename,
                current_path=str(file_path),
                content=content,
                content_type=content_type
            )
            file_id = reg["id"]
            
            with open(file_path, "wb") as buffer:
                buffer.write(content)

            logger.info(f"File uploaded: {file_path}, Size: {len(content)} bytes, ID: {file_id}")

            if ext == ".pdf":
                logger.info(f"Saved {file_path} to input folder. Delegating pipeline processing.")
            elif ext in [".md", ".txt"]:
                from config import KNOWLEDGE_BASE_DIR as _KB, UNCATEGORIZED_FOLDER as _UF
                final_md_dir = Path(_KB) / _UF
                final_md_dir.mkdir(parents=True, exist_ok=True)
                final_md_path = final_md_dir / safe_filename

                import shutil
                shutil.move(str(file_path), str(final_md_path))

                from indexer import index_file
                background_tasks.add_task(index_file, str(final_md_path))
                
            from drive_sync import sync_upload_to_drive
            background_tasks.add_task(sync_upload_to_drive)
                
            results.append({
                "filename": file_path.name,
                "status": "uploaded",
                "path": str(file_path),
                "file_id": file_id,
                "original_name": filename
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
        from config import KNOWLEDGE_BASE_DIR
        target_path = Path(KNOWLEDGE_BASE_DIR) / file_path
        if not target_path.resolve().is_relative_to(Path(KNOWLEDGE_BASE_DIR).resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
           
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
            
        headers = {}
        if target_path.suffix.lower() == ".pdf":
            media_type = "application/pdf"
            from urllib.parse import quote
            safe_name = quote(target_path.name)
            headers["Content-Disposition"] = f"inline; filename*=utf-8''{safe_name}"
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
        
        from indexer import delete_from_index
        delete_from_index(str(request.file_path))
        
        from status_manager import OCRStatusManager
        OCRStatusManager().remove_status(str(request.file_path))
        
        files_to_delete = [target_path]
        
        if target_path.suffix.lower() == '.md':
            pdf_path = target_path.with_suffix('.pdf')
            if pdf_path.exists():
                files_to_delete.append(pdf_path)
        elif target_path.suffix.lower() == '.pdf':
            md_path = target_path.with_suffix('.md')
            if md_path.exists():
                files_to_delete.append(md_path)
                
        deleted_files = []
        for f in files_to_delete:
            try:
                os.remove(f)
                deleted_files.append(f.name)
            except Exception as e:
                logger.warning(f"Failed to delete {f.name}: {e}")
                
        return {"success": True, "deleted": deleted_files}
        
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
        from indexer import delete_from_index
        from status_manager import OCRStatusManager
        
        status_mgr = OCRStatusManager()
        deleted_count = 0
        errors = []
        
        for file_path in request.file_paths:
            try:
                target_path = Path(KNOWLEDGE_BASE_DIR) / file_path
                if not target_path.resolve().is_relative_to(Path(KNOWLEDGE_BASE_DIR).resolve()):
                    errors.append(f"{file_path}: Access denied")
                    continue
                    
                if target_path.exists():
                    files_to_delete = [target_path]
                    if target_path.suffix.lower() == '.md':
                        pdf_path = target_path.with_suffix('.pdf')
                        if pdf_path.exists():
                            files_to_delete.append(pdf_path)
                    elif target_path.suffix.lower() == '.pdf':
                        md_path = target_path.with_suffix('.md')
                        if md_path.exists():
                            files_to_delete.append(md_path)
                            
                    for f in files_to_delete:
                        if f.exists():
                            f.unlink()
                
                delete_from_index(str(file_path))
                status_mgr.remove_status(str(file_path))
                deleted_count += 1
                
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}", exc_info=True)
                errors.append(f"{file_path}: {str(e)}")
                
        return {
            "status": "success", 
            "message": f"{deleted_count} files processed",
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
                if ext not in supported_exts and ext != '.md': 
                    continue
                
                item_rel_path = str(item.relative_to(root_path))
                ocr_status = "none"
                ocr_progress = None
                
                if ext == '.pdf':
                    md_path = item.with_suffix('.md')
                    if md_path.exists():
                        ocr_status = "completed"
                    
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
        from status_manager import OCRStatusManager
        status_mgr = OCRStatusManager()
        progress_data = status_mgr.get_all_status()
        
        return build_tree_recursive(Path(KNOWLEDGE_BASE_DIR), Path(KNOWLEDGE_BASE_DIR), progress_data, SUPPORTED_EXTENSIONS)
    except Exception as e:
        logger.error(f"Failed to generate file tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="File tree generation failed")

@router.get("/api/files/{file_id}/info")
def get_file_info(file_id: str):
    """ファイル情報を取得（ステータス、パス、同期状態等）"""
    try:
        import file_store
        info = file_store.get_file(file_id)
        if not info:
            raise HTTPException(status_code=404, detail="File not found")
        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve file info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="File info retrieval failed")
