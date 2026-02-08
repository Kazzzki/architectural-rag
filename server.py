import patch_importlib  # 最優先で実行
import os
import sys
# 以前のパッチは patch_importlib.py に移動したので削除
# (重複しても問題ないがキレイにする)

import shutil

import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse
from pydantic import BaseModel

from config import (
    CORS_ORIGINS,
    KNOWLEDGE_BASE_DIR,
    SUPPORTED_EXTENSIONS,
    GEMINI_API_KEY,
)
from retriever import search, build_context, get_source_files, get_db_stats
from generator import generate_answer, generate_answer_stream
from ocr_processor import process_pdf_background
from indexer import build_index, scan_files

# Gemini API設定
import google.generativeai as genai
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI(
    title="建築意匠ナレッジRAG API",
    description="建築PM/CM業務向けナレッジ検索・回答生成API",
    version="1.0.0",
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# リクエスト/レスポンスモデル
class ChatRequest(BaseModel):
    question: str
    category: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]


class StatsResponse(BaseModel):
    file_count: int
    chunk_count: int
    last_updated: str


class IndexResponse(BaseModel):
    total_files: int
    indexed: int
    skipped: int
    errors: int
    chunks: int


class FileInfo(BaseModel):
    filename: str
    category: str
    size_kb: float
    uploaded_at: str


# エンドポイント
@app.get("/")
async def root():
    return {"message": "建築意匠ナレッジRAG API", "status": "running"}


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """質問に対する回答を生成"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    try:
        # ベクトル検索
        search_results = search(request.question, filter_category=request.category)
        
        # コンテキスト構築
        context = build_context(search_results)
        
        # ソースファイル取得
        source_files = get_source_files(search_results)
        
        # 回答生成
        answer = generate_answer(request.question, context, source_files)
        
        return ChatResponse(answer=answer, sources=source_files)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """ストリーミング形式で回答を生成"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    try:
        search_results = search(request.question, filter_category=request.category)
        context = build_context(search_results)
        source_files = get_source_files(search_results)
        
        async def generate():
            async for chunk in generate_answer_stream(request.question, context, source_files):
                yield chunk
        
        return StreamingResponse(generate(), media_type="text/plain")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """データベース統計を取得"""
    stats = get_db_stats()
    return StatsResponse(
        file_count=stats["file_count"],
        chunk_count=stats["chunk_count"],
        last_updated=stats["last_updated"] or "未インデックス",
    )


@app.post("/api/index", response_model=IndexResponse)
async def rebuild_index(force: bool = False):
    """インデックスを再構築"""
    try:
        stats = build_index(force_rebuild=force)
        return IndexResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = "uploads"
):
    """ファイルをアップロード"""
    # 拡張子チェック
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"サポートされていないファイル形式です: {ext}"
        )
    
    # 保存ディレクトリ
    save_dir = Path(KNOWLEDGE_BASE_DIR) / category
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # ファイル保存
    file_path = save_dir / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    # PDFなら自動分類パイプラインをバックグラウンドで実行
    if ext == '.pdf':
        from pipeline_manager import process_file_pipeline
        # 出力パスはパイプライン内で自動決定されるため、ファイルパスのみ渡す
        # md_filename は process_file_pipeline の内部デフォルトに任せる
        background_tasks.add_task(process_file_pipeline, str(file_path))
    
    return FileInfo(
        filename=file.filename,
        category=category,
        size_kb=round(file_path.stat().st_size / 1024, 2),
        uploaded_at=datetime.now().isoformat(),
    )


@app.post("/api/upload/multiple")
async def upload_multiple_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    category: str = "uploads"
):
    """複数ファイルをアップロード"""
    results = []
    errors = []
    
    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            errors.append({"filename": file.filename, "error": f"未対応形式: {ext}"})
            continue
        
        try:
            save_dir = Path(KNOWLEDGE_BASE_DIR) / category
            save_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = save_dir / file.filename
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            # PDFなら自動分類パイプラインをバックグラウンドで実行
            if ext == '.pdf':
                from pipeline_manager import process_file_pipeline
                background_tasks.add_task(process_file_pipeline, str(file_path))

            results.append({
                "filename": file.filename,
                "category": category,
                "size_kb": round(file_path.stat().st_size / 1024, 2),
            })
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})
    
    return {"uploaded": results, "errors": errors}


@app.get("/api/files")
async def list_files():
    """アップロード済みファイル一覧"""
    files = scan_files()
    return {"files": files, "count": len(files)}


@app.get("/api/files/view/{file_path:path}")
async def view_file(file_path: str):
    """ファイルを閲覧・ダウンロード"""
    try:
        # ディレクトリトラバーサル防止
        target_path = Path(KNOWLEDGE_BASE_DIR) / file_path
        if not target_path.resolve().is_relative_to(Path(KNOWLEDGE_BASE_DIR).resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
           
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
            
        return FileResponse(target_path, filename=target_path.name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/system/export-source")
async def export_source():
    """ソースコード一式をZIPでダウンロード"""
    try:
        import zipfile
        from io import BytesIO
        from datetime import datetime
        
        # 除外設定
        EXCLUDE_DIRS = {
            'node_modules', 'venv', '.git', '__pycache__', 
            'knowledge_base', 'chroma_db', '.next', '.idea', '.vscode',
            'brain', '.gemini', 'artifacts' # Agentic artifacts
        }
        EXCLUDE_FILES = {
            '.DS_Store', 'ocr_progress.json', 'file_index.json', 'credentials.json'
        }
        
        # メモリバッファ作成
        zip_buffer = BytesIO()
        base_dir = Path(__file__).parent.resolve()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(base_dir):
                # 除外ディレクトリをリストから削除（in-place変更でその後のwalkをスキップ）
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                
                for file in files:
                    if file in EXCLUDE_FILES or file.endswith('.webp') or file.endswith('.png'):
                        continue
                        
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(base_dir)
                    zf.write(file_path, arcname)
                    
        zip_buffer.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"antigravity_source_{timestamp}.zip"
        
        # FastAPIのResponseだとストリーミングが難しい場合があるので、
        # uvicornならStreamingResponseを使うのが良いが、
        # ディスク容量を食わないようにメモリで作って一括で返す（小規模ならOK）
        
        from fastapi.responses import StreamingResponse
        
        return StreamingResponse(
            iter([zip_buffer.getvalue()]), 
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        print(f"Export error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class DeleteFileRequest(BaseModel):
    file_path: str


@app.delete("/api/files/delete")
async def delete_file(request: DeleteFileRequest):
    """ファイルを削除（物理ファイル＋インデックス）"""
    try:
        from config import KNOWLEDGE_BASE_DIR
        
        # ディレクトリトラバーサル防止
        target_path = Path(KNOWLEDGE_BASE_DIR) / request.file_path
        if not target_path.resolve().is_relative_to(Path(KNOWLEDGE_BASE_DIR).resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
            
        if not target_path.exists():
             raise HTTPException(status_code=404, detail="File not found")
        
        # 1. インデックスから削除
        from indexer import delete_from_index
        delete_from_index(str(request.file_path))
        
        # 2. ステータスから削除
        from status_manager import OCRStatusManager
        OCRStatusManager().remove_status(str(request.file_path))
        
        # 3. 物理ファイル削除
        # Markdownなら対になるPDFも削除、PDFなら対になるMarkdownも削除
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
                print(f"削除エラー ({f.name}): {e}")
                
        return {"success": True, "deleted": deleted_files}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def build_tree_recursive(current_path: Path, root_path: Path, ocr_progress_data: dict):
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
                node["children"].append(build_tree_recursive(item, root_path, ocr_progress_data))
            else:
                ext = item.suffix.lower()
                # 表示対象の拡張子（.mdも含める）
                if ext not in SUPPORTED_EXTENSIONS and ext != '.md': 
                    continue
                
                item_rel_path = str(item.relative_to(root_path))
                ocr_status = "none"
                ocr_progress = None
                
                if ext == '.pdf':
                    # Status Managerから情報を取得
                    if item_rel_path in ocr_progress_data:
                        progress_info = ocr_progress_data[item_rel_path]
                        status = progress_info.get("status")
                        # マネージャーのステータスを優先
                        if status == "processing":
                            ocr_status = "processing"
                            ocr_progress = {
                                "current": progress_info.get("processed_pages", 0),
                                "total": progress_info.get("total_pages", 1),
                                "estimated_remaining": progress_info.get("estimated_remaining")
                            }
                        elif status == "completed":
                            ocr_status = "completed"
                        elif status == "failed":
                            ocr_status = "failed"
                            ocr_progress = {"error": progress_info.get("error")}
                    
                    # JSONに情報がない場合のフォールバック（既存ロジック）
                    if ocr_status == "none":
                         md_path = item.with_suffix('.md')
                         if md_path.exists():
                             ocr_status = "completed"

                node["children"].append({
                    "name": item.name,
                    "type": "file",
                    "path": item_rel_path,
                    "size": item.stat().st_size,
                    "ocr_status": ocr_status,
                    "ocr_progress": ocr_progress
                })
    except Exception as e:
        print(f"Tree build error: {e}")
        
    return node


@app.get("/api/files/tree")
async def get_files_tree():
    """ファイルツリーを取得"""
    from status_manager import OCRStatusManager
    status_mgr = OCRStatusManager()
    progress_data = status_mgr.get_all_status()
    
    return build_tree_recursive(Path(KNOWLEDGE_BASE_DIR), Path(KNOWLEDGE_BASE_DIR), progress_data)


@app.get("/api/categories")
async def list_categories():
    """利用可能なカテゴリ一覧"""
    categories = [
        {"value": None, "label": "全て（横断検索）"},
        {"value": "01_カタログ", "label": "01_カタログ"},
        {"value": "02_図面", "label": "02_図面"},
        {"value": "03_技術基準", "label": "03_技術基準"},
        {"value": "04_リサーチ成果物", "label": "04_リサーチ成果物"},
        {"value": "uploads", "label": "アップロード"},
    ]
    return {"categories": categories}


# ========== Google Drive 連携 ==========

@app.get("/api/drive/status")
async def drive_status():
    """Google Drive認証状態を確認"""
    try:
        from drive_sync import get_auth_status
        return get_auth_status()
    except ImportError:
        return {"authenticated": False, "message": "drive_sync モジュールがありません"}
    except Exception as e:
        return {"authenticated": False, "message": str(e)}


@app.post("/api/drive/auth")
async def drive_auth():
    """Google Drive認証URLを取得"""
    try:
        from drive_sync import get_auth_url
        url = get_auth_url()
        return {"success": True, "auth_url": url}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()  # サーバーログに出力
        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()}")


@app.get("/api/drive/callback")
async def drive_callback(code: str):
    """Googleからのリダイレクトを受け取り認証完了"""
    try:
        from drive_sync import save_credentials_from_code
        save_credentials_from_code(code)
        # 完了後にトップページへリダイレクト
        return RedirectResponse(url="http://localhost:3000/?auth=success")
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/drive/upload")
async def drive_upload(background_tasks: BackgroundTasks):
    """Google Driveへバックアップ"""
    try:
        from drive_sync import backup_to_drive
        background_tasks.add_task(backup_to_drive)
        return {"status": "success", "message": "バックアップを開始しました"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DriveSyncRequest(BaseModel):
    folder_name: str = "建築意匠ナレッジDB"


@app.post("/api/drive/sync")
async def drive_sync(request: DriveSyncRequest):
    """Google Driveフォルダを同期"""
    try:
        from drive_sync import find_folder_by_name, sync_drive_folder
        
        # フォルダIDを検索
        folder_id = find_folder_by_name(request.folder_name)
        if not folder_id:
            raise HTTPException(
                status_code=404,
                detail=f"フォルダ '{request.folder_name}' が見つかりません"
            )
        
        # 同期実行
        stats = sync_drive_folder(folder_id, request.folder_name)
        return {
            "success": True,
            "folder_name": request.folder_name,
            **stats
        }
    except ImportError:
        raise HTTPException(status_code=500, detail="drive_sync モジュールがありません")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/drive/folders")
async def drive_list_folders(parent_id: str = "root"):
    """Google Driveのフォルダ一覧を取得"""
    try:
        from drive_sync import get_drive_service, list_drive_folders
        service = get_drive_service()
        folders = list_drive_folders(service, parent_id)
        return {"folders": folders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/sync-drive")
async def sync_to_drive():
    """ローカルの整理済みフォルダをGoogle Driveに同期（アップロード）"""
    try:
        from drive_sync import sync_upload_to_drive
        # 同期実行 (完了まで待機)
        result = sync_upload_to_drive()
        if result.get("status") == "error":
             raise HTTPException(status_code=500, detail=result.get("message"))
        return result
    except ImportError:
        raise HTTPException(status_code=500, detail="drive_sync module not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

