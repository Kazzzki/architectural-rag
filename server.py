import patch_importlib  # 最優先で実行
import os
import sys

# システム全体のデフォルトエンコーディングをUTF-8に強制（日本語ファイル名/パスのセーフティネット）
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

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
from logging.handlers import RotatingFileHandler

# Logging setup (Phase 6 — ログローテーション対応 #16)
_log_handler = RotatingFileHandler(
    'app.log',
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding='utf-8',
)
_log_handler.setLevel(logging.INFO)
_log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_log_handler.setFormatter(_log_formatter)

# Console handler
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(_log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_log_handler, console])

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
        # 認証不要のパス (Google Driveコールバック等は外部から直接リダイレクトされるため除外)
        EXEMPT_PATHS = {"/api/health", "/docs", "/openapi.json", "/api/drive/callback"}

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

if APP_PASSWORD:
    logger.info("🔒 Basic認証が有効です (APP_PASSWORD設定済)")
else:
    logger.warning("⚠️  APP_PASSWORDが未設定——全APIエンドポイントが認証なしで公開状態です。")
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: 起動・シャットダウン時の処理"""
    # データベース初期化
    from database import init_db, get_session, Job, LegacyDocument, DocumentVersion
    from sqlalchemy import text
    
    init_db()
    
    # クラッシュ等による処理中ステータスの固着をリセット
    try:
        session = get_session()
        # jobs テーブル
        session.execute(text("UPDATE jobs SET status = 'failed', error_message = 'Server restarted' WHERE status = 'running'"))
        
        # LegacyDocument (旧モデル) — 処理中扱いの全ステータスをリセット
        # 'processing' だけでなく 'indexing', 'ocr_completed', 'enriched', 'uploading_to_drive' も
        # サーバー再起動時にはスタックしているので failed にリセットする
        session.execute(text(
            "UPDATE legacy_documents "
            "SET status = 'failed', error_message = 'Server restarted during processing' "
            "WHERE status IN ('processing', 'indexing', 'ocr_completed', 'enriched', "
            "                 'uploading_to_drive', 'drive_synced')"
        ))
        
        # DocumentVersion (新モデル) — 同様に中間ステータスをリセット
        session.execute(text(
            "UPDATE document_versions "
            "SET ingest_status = 'failed', error_message = 'Server restarted during processing' "
            "WHERE ingest_status IN ('accepted', 'ocr_processing', 'indexing', "
            "                        'ocr_completed', 'enriched', 'uploading_to_drive', 'drive_synced')"
        ))
        
        session.commit()
    except Exception as e:
        logger.warning(f"Resetting stuck jobs failed: {e}")
    finally:
        session.close()

    # 課題因果メモのインデックスを既存 Markdown ファイルと同期
    try:
        from issue_memo_indexer import IssueMemoIndexer
        indexer = IssueMemoIndexer()
        count = indexer.reindex_all()
        logger.info(f"Issue memo index synced: {count} files")
    except Exception as e:
        logger.warning(f"Issue memo reindex failed (non-fatal): {e}")

    yield
    # シャットダウン時の処理（将来必要に応じて追加）


app = FastAPI(
    title="建築意匠ナレッジRAG API",
    description="建築PM/CM業務向けナレッジ検索・回答生成API",
    version="1.0.0",
    lifespan=lifespan,
)

# 認証ミドルウェアを登録
if APP_PASSWORD:
    app.add_middleware(BasicAuthMiddleware)


# @app.on_event("startup")
# def startup_event():
#     def background_build_index():
#         try:
#             print("Starting background index build...")
#             build_index(force_rebuild=False)
#             print("Background index build completed.")
#         except Exception as e:
#             print(f"Background index build failed: {e}")
#             import traceback
#             traceback.print_exc()
#             
#     threading.Thread(target=background_build_index, daemon=True).start()

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


# ====== Routers マウント ======
from routers import system, chat, pdf, drive, tags, files, personal_context, analyze, projects

app.include_router(system.router)
app.include_router(chat.router)
app.include_router(pdf.router)
app.include_router(drive.router)
app.include_router(tags.router)
app.include_router(files.router)
app.include_router(personal_context.router)
app.include_router(analyze.router)
app.include_router(projects.router)
from routers.research import router as research_router
app.include_router(research_router)
from routers import issues as issues_module
app.include_router(issues_module.router)
from routers import transcribe as transcribe_module
app.include_router(transcribe_module.router)
from routers import tasks as tasks_module
app.include_router(tasks_module.router)
from routers import meetings as meetings_module
app.include_router(meetings_module.router)

@app.get("/")
async def root():
    return {"message": "建築意匠ナレッジRAG API", "status": "running"}


@app.get("/api/models", tags=["Meta"])
async def list_models():
    """利用可能なモデル一覧を返す。フロントエンドのセレクター生成に使用。"""
    from config import AVAILABLE_MODELS
    return AVAILABLE_MODELS


@app.get("/api/roles", tags=["Meta"])
async def list_roles():
    """利用可能なロール一覧を返す。フロントエンドのセレクター生成に使用。"""
    from prompts.context_sheet_roles import AVAILABLE_ROLES
    return AVAILABLE_ROLES


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

