from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import logging
import traceback

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Google Drive Sync"])

class DriveSyncRequest(BaseModel):
    folder_name: str = "建築意匠ナレッジDB"

@router.get("/api/drive/status")
def drive_status():
    """Google Drive認証状態を確認"""
    try:
        from drive_sync import get_auth_status
        return get_auth_status()
    except ImportError:
        return {"authenticated": False, "message": "drive_sync モジュールがありません"}
    except Exception as e:
        logger.error(f"Failed to get drive status: {e}", exc_info=True)
        return {"authenticated": False, "message": str(e)}

@router.post("/api/drive/auth")
def drive_auth(request: Request):
    """Google Drive認証URLを取得"""
    try:
        from drive_sync import get_auth_url
        
        origin = request.headers.get("origin")
        if not origin:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
            host = request.headers.get("x-forwarded-host", request.url.netloc)
            origin = f"{scheme}://{host}"
            
        redirect_uri = f"{origin}/api/drive/callback"
        
        url = get_auth_url(redirect_uri=redirect_uri)
        return {"success": True, "auth_url": url}
    except FileNotFoundError as e:
        logger.warning(f"Drive auth file not found: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Drive auth error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()}")

@router.get("/api/drive/callback")
def drive_callback(request: Request, code: str):
    """Googleからのリダイレクトを受け取り認証完了"""
    try:
        from drive_sync import save_credentials_from_code
        
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.url.netloc)
        origin = f"{scheme}://{host}"
        
        redirect_uri = f"{origin}/api/drive/callback"
        save_credentials_from_code(code, redirect_uri=redirect_uri)
        
        return RedirectResponse(url=f"{origin}/?auth=success")
    except Exception as e:
        logger.error(f"Drive callback error: {e}", exc_info=True)
        return {"error": str(e)}

@router.post("/api/drive/upload")
async def drive_upload(background_tasks: BackgroundTasks):
    """Google Driveへバックアップ"""
    try:
        from drive_sync import backup_to_drive
        background_tasks.add_task(backup_to_drive)
        return {"status": "success", "message": "バックアップを開始しました"}
    except Exception as e:
        logger.error(f"Drive backup start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Drive backup execution failed")

@router.post("/api/drive/sync")
async def drive_sync(request: DriveSyncRequest):
    """Google Driveフォルダを同期"""
    try:
        from drive_sync import find_folder_by_name, sync_drive_folder
        
        folder_id = find_folder_by_name(request.folder_name)
        if not folder_id:
            raise HTTPException(
                status_code=404,
                detail=f"フォルダ '{request.folder_name}' が見つかりません"
            )
        
        stats = sync_drive_folder(folder_id, request.folder_name)
        return {
            "success": True,
            "folder_name": request.folder_name,
            **stats
        }
    except ImportError:
        raise HTTPException(status_code=500, detail="drive_sync モジュールがありません")
    except Exception as e:
        logger.error(f"Drive sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Drive sync failed")

@router.get("/api/drive/folders")
async def drive_list_folders(parent_id: str = "root"):
    """Google Driveのフォルダ一覧を取得"""
    try:
        from drive_sync import get_drive_service, list_drive_folders
        service = get_drive_service()
        folders = list_drive_folders(service, parent_id)
        return {"folders": folders}
    except Exception as e:
        logger.error(f"Failed to list drive folders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve folders")

@router.post("/api/sync-drive")
async def sync_to_drive():
    """ローカルの整理済みフォルダをGoogle Driveに同期（Local -> Drive Mirror Upload）"""
    try:
        folder_name = "建築意匠ナレッジDB"
        
        from drive_sync import find_folder_by_name, create_folder, get_drive_service
        from config import KNOWLEDGE_BASE_DIR
        
        service = get_drive_service()
        folder_id = find_folder_by_name(folder_name)
        if not folder_id:
            folder_id = create_folder(service, folder_name)
            
        from drive_sync import upload_mirror_to_drive
        result = upload_mirror_to_drive(str(KNOWLEDGE_BASE_DIR), folder_id)
        
        return result
    except ImportError:
        raise HTTPException(status_code=500, detail="drive_sync module not found")
    except Exception as e:
        logger.error(f"Mirror upload to drive failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Mirror upload failed")
