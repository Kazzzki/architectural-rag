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
                except Exception:
                    pass
            
            if authenticated:
                return await call_next(request)

            return Response(
                content="認証が必要です",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Antigravity RAG"'},
            )

    print("🔒 Basic認証が有効です (APP_PASSWORD設定済)")
else:
    logger.warning("⚠️  APP_PASSWORDが未設定——全APIエンドポイントが認証なしで公開状態です。")


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


# ====== Routers マウント ======
from routers.system import router as system_router
from routers.chat import router as chat_router
from routers.pdf import router as pdf_router
from routers.drive import router as drive_router
from routers.tags import router as tags_router
from routers.files import router as files_router

app.include_router(system_router)
app.include_router(chat_router)
app.include_router(pdf_router)
app.include_router(drive_router)
app.include_router(tags_router)
app.include_router(files_router)

@app.get("/")
async def root():
    return {"message": "建築意匠ナレッジRAG API", "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

