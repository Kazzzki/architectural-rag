import patch_importlib  # 最優先で実行
import os
import sys
# 以前のパッチは patch_importlib.py に移動したので削除
# (重複しても問題ないがキレイにする)

import shutil
import time
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import secrets
# Logging setup (Phase 3)
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
# Console handler
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

logger = logging.getLogger(__name__)

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

import gemini_client  # 共有クライアント初期化

# Basic認証設定（ミドルウェアで全API保護）
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

if APP_PASSWORD:
    import base64
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response

    class BasicAuthMiddleware(BaseHTTPMiddleware):
        """APP_PASSWORD設定時に全APIリクエストをBasic認証で保護"""
        # 認証不要のパス
        EXEMPT_PATHS = {"/api/health", "/docs", "/openapi.json"}

        async def dispatch(self, request, call_next):
            path = request.url.path

            # 認証不要パスはスキップ
            if path in self.EXEMPT_PATHS:
                return await call_next(request)

            # OPTIONSメソッド（CORSプリフライト）はスキップ
            if request.method == "OPTIONS":
                return await call_next(request)

            # 静的ファイル・非APIパスはスキップ
            if not path.startswith("/api/"):
                return await call_next(request)

            # Authorization ヘッダーを検証
            auth = request.headers.get("Authorization")
            authenticated = False
            if auth and auth.startswith("Basic "):
                try:
                    decoded = base64.b64decode(auth[6:]).decode("utf-8")
                    _, password = decoded.split(":", 1)
                    if secrets.compare_digest(password, APP_PASSWORD):
                        authenticated = True
                except (ValueError, TypeError, base64.binascii.Error) as e:
                    logger.warning(f"Basic Auth decode error: {e}")
            
            if authenticated:
                return await call_next(request)

            return Response(
                content="認証が必要です",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Antigravity RAG"'},
            )

    print("🔒 Basic認証が有効です (APP_PASSWORD設定済)")
else:
    print("⚠️  APP_PASSWORDが未設定のため、認証なしで動作します")


app = FastAPI(
    title="建築意匠ナレッジRAG API",
    description="建築PM/CM業務向けナレッジ検索・回答生成API",
    version="1.0.0",
)

# 認証ミドルウェアを登録
if APP_PASSWORD:
    app.add_middleware(BasicAuthMiddleware)

# データベース初期化
from database import init_db, migrate_from_json
init_db()
# 初回起動時に既存JSONデータをDBへ移行
try:
    migrate_from_json()
except Exception as e:
    print(f"JSON migration skipped or error: {e}")

import threading
@app.on_event("startup")
def startup_event():
    def background_build_index():
        try:
            print("Starting background index build...")
            build_index(force_rebuild=False)
            print("Background index build completed.")
        except Exception as e:
            print(f"Background index build failed: {e}")
            import traceback
            traceback.print_exc()
            
    threading.Thread(target=background_build_index, daemon=True).start()

# マインドマップルーターをマウント
from mindmap.router import router as mindmap_router
app.include_router(mindmap_router)

# Global Exception Handler (Phase 3 -> RAG v2 Update)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {exc}\n"
        f"Path: {request.url.path}\n"
        f"Traceback:\n{traceback.format_exc()}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "サーバー内部エラーが発生しました。管理者に連絡してください。"}
    )

# CORS設定 (ngrok対応)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # config.pyで定義されたオリジン
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# リクエスト/レスポンスモデル
class ChatRequest(BaseModel):
    question: str
    category: Optional[str] = None
    file_type: Optional[str] = None
    date_range: Optional[str] = None
    tags: Optional[List[str]] = None
    tag_match_mode: Optional[str] = "any"
    history: Optional[List[dict]] = None  # [{role: "user"|"assistant", content: str}]


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
    """
    外形監視用ヘルスチェック。
    ChromaDB・SQLite・Gemini API・Google Drive・ファイルストレージの疎通を確認する。
    """
    from datetime import datetime as _dt, timezone as _tz

    status = {
        "server": "ok",
        "chromadb": "unknown",
        "sqlite": "unknown",
        "gemini_api": "unknown",
        "google_drive": "unknown",
        "file_storage": "unknown",
    }

    # 1. ChromaDB確認
    from retriever import get_collection
    try:
        collection = get_collection()
        count = collection.count()
        status["chromadb"] = f"ok ({count} chunks)"
    except Exception as e:
        status["chromadb"] = f"error: {e}"

    # 2. SQLite確認
    from database import get_session
    try:
        session = get_session()
        from sqlalchemy import text
        session.execute(text("SELECT 1"))
        session.close()
        status["sqlite"] = "ok"
    except Exception as e:
        status["sqlite"] = f"error: {e}"

    # 3. Gemini API確認（軽量リクエスト）
    try:
        from gemini_client import get_client
        from config import EMBEDDING_MODEL
        client = get_client()
        client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents='ping'
        )
        status["gemini_api"] = "ok"
    except Exception as e:
        status["gemini_api"] = f"error: {e}"

    # 4. Google Drive認証確認
    try:
        from drive_sync import get_auth_status
        drive_info = get_auth_status()
        if drive_info.get("authenticated"):
            status["google_drive"] = "ok"
        else:
            status["google_drive"] = f"not authenticated: {drive_info.get('message', '')}"
    except Exception as e:
        status["google_drive"] = f"error: {e}"

    # 5. ファイルストレージ確認
    try:
        from indexer import scan_files
        files = scan_files()
        status["file_storage"] = f"ok ({len(files)} files)"
    except Exception as e:
        status["file_storage"] = f"error: {e}"

    # 全体ステータス判定
    error_count = sum(1 for v in status.values() if str(v).startswith("error"))
    warn_count = sum(1 for v in status.values() if "not authenticated" in str(v) or v == "unknown")
    if error_count > 0:
        overall = "error"
    elif warn_count > 0:
        overall = "degraded"
    else:
        overall = "ok"

    result = {
        "status": overall,
        "services": status,
        "timestamp": _dt.now(_tz.utc).isoformat(),
    }

    all_ok = overall == "ok"
    return JSONResponse(
        content=result,
        status_code=200 if all_ok or overall == "degraded" else 503
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """質問に対する回答を生成"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    try:
        # ベクトル検索（タグ・タグマッチモードも渡す）
        search_results = search(
            request.question,
            filter_category=request.category,
            filter_file_type=request.file_type,
            filter_date_range=request.date_range,
            filter_tags=request.tags,
            tag_match_mode=request.tag_match_mode or "any",
        )

        logger.info(f"Query: {request.question}, Results: {len(search_results.get('documents', []))}")

        # コンテキスト構築
        context = build_context(search_results)

        # ソースファイル取得
        source_files = get_source_files(search_results)

        # 回答生成（会話履歴を渡す）
        answer = generate_answer(request.question, context, source_files, history=request.history)

        logger.info(f"Answer generated ({len(answer)} chars)")

        return ChatResponse(answer=answer, sources=source_files)

    except RuntimeError as e:
        logger.error(f"Gemini API完全失敗: {e}")
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"予期しないエラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """ストリーミング形式で回答を生成 (Phase 2: SSE対応)"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    try:
        # ベクトル検索（タグ・タグマッチモードも渡す）
        search_results = search(
            request.question,
            filter_category=request.category,
            filter_file_type=request.file_type,
            filter_date_range=request.date_range,
            filter_tags=request.tags,
            tag_match_mode=request.tag_match_mode or "any",
        )
        context = build_context(search_results)
        source_files = get_source_files(search_results)
        history = request.history

        async def generate():
            import json
            # 1. ソース情報を先に送信
            yield f"data: {json.dumps({'type': 'sources', 'data': source_files}, ensure_ascii=False)}\n\n"

            try:
                # 2. 回答をストリーミング（会話履歴を渡す）
                async for chunk in generate_answer_stream(request.question, context, source_files, history=history):
                    yield f"data: {json.dumps({'type': 'answer', 'data': chunk}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Stream exception: {e}")
                # エラーイベントとして送信し、フロントでハンドリングできるようにする
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

            # 3. 完了シグナル
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(), 
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        logger.error(f"Stream Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    """データベース統計を取得"""
    stats = get_db_stats()
    return StatsResponse(
        file_count=stats["file_count"],
        chunk_count=stats["chunk_count"],
        last_updated=stats["last_updated"] or "未インデックス",
    )


@app.get("/api/ocr/status")
def get_ocr_status():
    """OCR処理中・最近処理したファイルのステータスを返す"""
    try:
        from database import get_session, Document
        session = get_session()
        try:
            # processingまたは最近completedになったもの
            recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
            docs = session.query(Document).filter(
                (Document.status == "processing") |
                (Document.status == "failed") |
                ((Document.status == "completed") & (Document.updated_at >= recent_cutoff))
            ).order_by(Document.updated_at.desc()).limit(20).all()
            
            jobs = []
            for doc in docs:
                jobs.append({
                    "file_path": doc.file_path,
                    "filename": doc.filename,
                    "status": doc.status,
                    "processed_pages": doc.processed_pages or 0,
                    "total_pages": doc.total_pages or 1,
                    "error_message": doc.error_message,
                    "estimated_remaining": doc.estimated_remaining,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                })
            
            processing_count = sum(1 for j in jobs if j["status"] == "processing")
            return {
                "processing_count": processing_count,
                "jobs": jobs
            }
        finally:
            session.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/ocr/status/{file_path:path}")
def dismiss_ocr_status(file_path: str):
    """OCRステータスエントリを削除（非表示化）"""
    try:
        from status_manager import OCRStatusManager
        OCRStatusManager().remove_status(file_path)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/index", response_model=IndexResponse)
def rebuild_index(force: bool = False):
    """インデックスを再構築"""
    try:
        stats = build_index(force_rebuild=force)
        return IndexResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Old upload_file implementation removed to avoid duplicate endpoint


@app.post("/api/upload/multiple")
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

    # アップロード直後は未分類フォルダへ（OCR後に自動カテゴリへ移動）
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
        # オリジナルのファイル名を維持しつつ、ファイルシステム上で危険な文字のみ除去する
        # werkzeug の secure_filename() は日本語を除去してしまうため使わない
        safe_filename = re.sub(r'[/\\:*?"<>|]', '_', filename).strip()
        # ドットのみ・空・拡張子のみになった場合はタイムスタンプ名にフォールバック
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
                # PDFはinputフォルダに保存してdaemon経由でOCRパイプラインへ
                # (FastAPIスレッドから直接起動するとwatchdogと競合するため委譲)
                logger.info(f"Saved {file_path} to input folder. Delegating pipeline processing to antigravity_daemon.")
            elif ext in [".md", ".txt"]:
                # Markdown/TextはOCR不要: 直接 00_未分類 に配置してインデックス
                from config import KNOWLEDGE_BASE_DIR as _KB, UNCATEGORIZED_FOLDER as _UF
                final_md_dir = Path(_KB) / _UF
                final_md_dir.mkdir(parents=True, exist_ok=True)
                final_md_path = final_md_dir / safe_filename

                import shutil
                shutil.move(str(file_path), str(final_md_path))

                from indexer import index_file
                background_tasks.add_task(index_file, str(final_md_path))
                
            # Google Driveへの自動バックアップタスク追加
            from drive_sync import sync_upload_to_drive
            # ファイル単体のアップロードがモジュールに無いため、ファイルが含まれるディレクトリ全体の増分同期をキックする
            # （重い場合は個別にファイルアップロードする関数をdrive_syncに追加するのが理想的）
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


@app.get("/api/files")
def list_files():
    """アップロード済みファイル一覧"""
    files = scan_files()
    return {"files": files, "count": len(files)}


@app.get("/api/files/view/{file_path:path}")
async def view_file(file_path: str):
    """ファイルを閲覧・ダウンロード"""
    try:
        # ディレクトリトラバーサル防止（KNOWLEDGE_BASE_DIR 以下のみ許可）
        target_path = Path(KNOWLEDGE_BASE_DIR) / file_path
        if not target_path.resolve().is_relative_to(Path(KNOWLEDGE_BASE_DIR).resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
           
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
            
        # PDFの場合はブラウザでインライン表示（プレビュー）できるようにする
        headers = {}
        if target_path.suffix.lower() == ".pdf":
            media_type = "application/pdf"
            # 日本語ファイル名はURLエンコードしておく
            from urllib.parse import quote
            safe_name = quote(target_path.name)
            headers["Content-Disposition"] = f"inline; filename*=utf-8''{safe_name}"
        else:
            media_type = "application/octet-stream"
            
        # filenameパラメータを直接渡すとContent-Dispositionがattachmentになる場合があるため、headersを使用
        if headers:
            return FileResponse(target_path, media_type=media_type, headers=headers)
        else:
            return FileResponse(target_path, filename=target_path.name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# NOTE: GET /api/pdf/{file_id} は get_pdf() に統合済み（file_storeフォールバック付き）
# NOTE: GET /api/pdf/metadata/{file_id} は get_pdf_metadata() に統合済み（pypdf対応）

@app.get("/api/pdf/list")
def list_pdfs():
    """保存済みPDFの一覧を取得"""
    from database import get_session, Document as DbDocument
    session = get_session()
    try:
        # file_hashが設定されているドキュメントの一覧
        docs = session.query(DbDocument).filter(
            DbDocument.file_hash.isnot(None), 
            DbDocument.file_type == "pdf"
        ).all()
        return [{"file_id": d.file_hash, "filename": d.filename} for d in docs]
    finally:
        session.close()




@app.get("/api/system/export-source")
async def export_source():
    """ソースコード一式をZIPでダウンロード"""
    try:
        import zipfile
        from io import BytesIO
        from datetime import datetime, timezone
        
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
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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
        print(f"Delete file error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class BulkDeleteRequest(BaseModel):
    file_paths: List[str]

@app.delete("/api/files/bulk-delete")
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
                # ディレクトリトラバーサル防止
                target_path = Path(KNOWLEDGE_BASE_DIR) / file_path
                if not target_path.resolve().is_relative_to(Path(KNOWLEDGE_BASE_DIR).resolve()):
                    errors.append(f"{file_path}: Access denied")
                    continue
                    
                if not target_path.exists():
                     pass
                else:
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
                print(f"Failed to delete {file_path}: {e}")
                errors.append(f"{file_path}: {str(e)}")
                
        return {
            "status": "success", 
            "message": f"{deleted_count} files processed",
            "errors": errors
        }
    except Exception as e:
        print(f"Bulk delete error: {e}")
        traceback.print_exc()
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
                    # まず .md ファイルの存在で完了確認（ファイル移動後でも確実に検出）
                    md_path = item.with_suffix('.md')
                    if md_path.exists():
                        ocr_status = "completed"
                    
                    # Status Managerからリアルタイム情報で上書き（processing/failed優先）
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
        print(f"Tree build error: {e}")
        
    return node


@app.get("/api/files/tree")
def get_files_tree():
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
        {"value": "01_カタログ", "label": "01 カタログ"},
        {"value": "02_図面", "label": "02 図面"},
        {"value": "03_技術基準", "label": "03 技術基準"},
        {"value": "04_リサーチ成果物", "label": "04 リサーチ成果物"},
        {"value": "05_法規", "label": "05 法規"},
        {"value": "06_設計マネジメント", "label": "06 設計マネジメント"},
        {"value": "07_コストマネジメント", "label": "07 コストマネジメント"},
        {"value": "00_未分類", "label": "00 未分類"},
    ]
    return {"categories": categories}


# ========== Google Drive 連携 ==========

@app.get("/api/drive/status")
def drive_status():
    """Google Drive認証状態を確認"""
    try:
        from drive_sync import get_auth_status
        return get_auth_status()
    except ImportError:
        return {"authenticated": False, "message": "drive_sync モジュールがありません"}
    except Exception as e:
        return {"authenticated": False, "message": str(e)}


@app.post("/api/drive/auth")
def drive_auth(request: Request):
    """Google Drive認証URLを取得"""
    try:
        from drive_sync import get_auth_url
        
        # リクエストからURLのベース部分を取得 (例: https://antigravity.rag-architecture.com)
        # Nginx/Cloudflareプロキシ等を経由している場合は Forwardedヘッダ や origin を優先使用
        origin = request.headers.get("origin")
        if not origin:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
            host = request.headers.get("x-forwarded-host", request.url.netloc)
            origin = f"{scheme}://{host}"
            
        redirect_uri = f"{origin}/api/drive/callback"
        
        url = get_auth_url(redirect_uri=redirect_uri)
        return {"success": True, "auth_url": url}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()  # サーバーログに出力
        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()}")


@app.get("/api/drive/callback")
def drive_callback(request: Request, code: str):
    """Googleからのリダイレクトを受け取り認証完了"""
    try:
        from drive_sync import save_credentials_from_code
        
        # リクエストからURLのベース部分を取得
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.url.netloc)
        origin = f"{scheme}://{host}"
        
        redirect_uri = f"{origin}/api/drive/callback"
        save_credentials_from_code(code, redirect_uri=redirect_uri)
        
        # 完了後にトップページへリダイレクト
        return RedirectResponse(url=f"{origin}/?auth=success")
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
    """ローカルの整理済みフォルダをGoogle Driveに同期（Local -> Drive Mirror Upload）"""
    try:
        # フォルダ名は '建築意匠ナレッジDB' 固定、または環境変数から取得
        folder_name = "建築意匠ナレッジDB"
        
        # フォルダIDを取得 (存在しない場合は作成)
        from drive_sync import find_folder_by_name, create_folder, get_drive_service
        from config import KNOWLEDGE_BASE_DIR
        
        service = get_drive_service()
        folder_id = find_folder_by_name(folder_name)
        if not folder_id:
            folder_id = create_folder(service, folder_name)
            
        # 同期実行 (KNOWLEDGE_BASE_DIR 以下の全ファイルを対象)
        from drive_sync import upload_mirror_to_drive
        result = upload_mirror_to_drive(str(KNOWLEDGE_BASE_DIR), folder_id)
        
        return result
    except ImportError:
        raise HTTPException(status_code=500, detail="drive_sync module not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Web画面からアップロードされたファイルを保存し、file_storeに登録する。
    セキュリティ:
    - 許可された拡張子のみ受付
    - ファイルサイズ上限 100MB
    - ファイル名サニタイズ
    """
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    
    filename = file.filename or "unknown"
    filename = os.path.basename(filename)
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
    
    # ファイル名サニタイズ
    # werkzeug の secure_filename() は日本語を除去してしまうため使わない
    import re
    safe_filename = re.sub(r'[/\\:*?"<>|]', '_', filename).strip()
    if not safe_filename or safe_filename == ext or safe_filename.lstrip('.') == '':
        safe_filename = f"file_{int(time.time())}{ext}"
    if not safe_filename.lower().endswith(ext):
        safe_filename = safe_filename + ext
    
    # 入力フォルダ確保（ローカルに保存してGoogle Drive evictionを回避）
    from config import KNOWLEDGE_BASE_DIR, BASE_DIR
    input_dir = Path(BASE_DIR) / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    
    base_name = Path(safe_filename).stem
    file_path = input_dir / safe_filename
    timestamp = int(time.time())
    if file_path.exists():
        file_path = input_dir / f"{base_name}_{timestamp}{ext}"
    
    try:
        content = await file.read()
        
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
            )
        
        # file_storeに登録 (論理ID = SHA-256先頭16文字)
        import file_store
        content_type = "application/pdf" if ext == ".pdf" else f"image/{ext[1:]}"
        reg = file_store.register_file(
            original_name=filename,
            current_path=str(file_path),
            content=content,
            content_type=content_type
        )
        file_id = reg["id"]
        
        # inputフォルダに保存（OCR/分類パイプライン用）
        # 重複保存は停止: PDF_STORAGE_DIR への {file_id}.pdf コピーは廃止
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        logger.info(f"File uploaded: {file_path}, Size: {len(content)} bytes, ID: {file_id}")
        
        # 自動処理開始 (PDFのみ)
        if ext == ".pdf":
            from pipeline_manager import process_file_pipeline
            background_tasks.add_task(process_file_pipeline, str(file_path))
        elif ext in [".md", ".txt"]:
            from indexer import index_file
            # Markdown/TextファイルはOCR不要なため、直接インデックス（Chunking）に追加する
            background_tasks.add_task(index_file, str(file_path))

        # Google Driveへの自動バックアップタスク追加
        from drive_sync import sync_upload_to_drive
        background_tasks.add_task(sync_upload_to_drive)

        return {
            "filename": file_path.name, 
            "status": "uploaded", 
            "path": str(file_path),
            "file_id": file_id,
            "original_name": filename,
            "message": "File uploaded successfully. Automatic classification will start shortly."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========== PDF Delivery & File Info API ==========

@app.get("/api/pdf/{file_id}")
async def get_pdf(file_id: str):
    """PDFファイルをバイナリ配信（file_storeから解決、フォールバックあり）"""
    if not file_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid file_id")
    
    # 1. file_storeから取得を試みる
    try:
        import file_store
        file_info = file_store.get_file(file_id)
        if file_info:
            fp = Path(file_info["current_path"])
            if fp.exists():
                return FileResponse(fp, media_type="application/pdf",
                                   filename=file_info.get("original_name", fp.name))
    except Exception as e:
        logger.debug(f"file_store lookup failed: {e}")
    
    # 2. PDF_STORAGE_DIR内のID名ファイルにフォールバック
    from config import PDF_STORAGE_DIR
    target_path = Path(PDF_STORAGE_DIR) / f"{file_id}.pdf"
    if target_path.exists():
        return FileResponse(target_path, media_type="application/pdf")
    
    raise HTTPException(status_code=404, detail="PDF not found")


@app.get("/api/files/{file_id}/info")
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tags")
def get_tags():
    """利用可能なタグ一覧を取得"""
    try:
        import yaml
        base_dir = Path(".")
        rules_path = base_dir / "classification_rules.yaml"
        if not rules_path.exists():
            return {}
            
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = yaml.safe_load(f)
            
        return rules.get("available_tags", {})
    except Exception as e:
        logger.error(f"Failed to load tags: {e}")
        return {}

@app.get("/api/pdf/metadata/{file_id}")
async def get_pdf_metadata(file_id: str):
    """PDFメタデータ取得"""
    import pypdf
    from config import PDF_STORAGE_DIR
    
    if not file_id.isalnum():
         raise HTTPException(status_code=400, detail="Invalid file_id")

    target_path = Path(PDF_STORAGE_DIR) / f"{file_id}.pdf"
    
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
        
    try:
        reader = pypdf.PdfReader(target_path)
        return {
            "file_id": file_id,
            "page_count": len(reader.pages),
            "size_bytes": target_path.stat().st_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ========== 設定関連エンドポイント ==========

class GeminiKeyRequest(BaseModel):
    api_key: str

@app.get("/api/settings/gemini-key")
async def get_gemini_key():
    """設定済みのGemini APIキーを取得（セキュリティのため一部隠蔽）"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"api_key": "", "configured": False}
    
    # 前後数文字だけ表示
    if len(api_key) > 8:
        masked = f"{api_key[:4]}...{api_key[-4:]}"
    else:
        masked = "****"
        
    return {"api_key": masked, "configured": True}

@app.post("/api/settings/gemini-key")
async def set_gemini_key(request: GeminiKeyRequest):
    """Gemini APIキーを設定・保存"""
    new_key = request.api_key.strip()
    if not new_key:
        raise HTTPException(status_code=400, detail="APIキーが空です")
    
    # .envファイルを更新
    env_path = Path(".env")
    lines = []
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
    key_exists = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={new_key}\n")
            key_exists = True
        else:
            new_lines.append(line)
            
    if not key_exists:
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        new_lines.append(f"GEMINI_API_KEY={new_key}\n")
        
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
        
    # 環境変数とconfigを更新
    os.environ["GEMINI_API_KEY"] = new_key
    import config
    config.GEMINI_API_KEY = new_key
    
    # クライアントを再生成
    import gemini_client as _gc
    _gc.reconfigure(new_key)

    return {"message": "APIキーを保存しました"}

@app.post("/api/settings/test-gemini")
async def test_gemini_key():
    """現在のAPIキーでGemini接続テスト"""
    import config

    if not config.GEMINI_API_KEY:
        raise HTTPException(status_code=400, detail="APIキーが設定されていません")
        
    try:
        from google.genai import types as _types
        from gemini_client import get_client as _get_client
        _client = _get_client()
        _response = _client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Hello, this is a connection test.",
        )
        return {"success": True, "message": "接続テスト成功", "response": _response.text[:50]}
    except Exception as e:
        return {"success": False, "message": f"接続テスト失敗: {str(e)}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

