from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import os
import time
import logging
import traceback
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(tags=["System & Settings"])

# ========== モデル定義 ==========
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

class GeminiKeyRequest(BaseModel):
    api_key: str

# ========== エンドポイント ==========

@router.get("/api/health")
def health_check():
    """
    外形監視用ヘルスチェック。
    ChromaDB・SQLite・Gemini API・Google Drive・ファイルストレージの疎通を確認する。
    """
    from datetime import datetime as _dt
    import sys

    print("HEALTH CHECK STARTING...", file=sys.stderr)

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
        print("Checking ChromaDB...", file=sys.stderr)
        collection = get_collection()
        count = collection.count()
        status["chromadb"] = f"ok ({count} chunks)"
        print("ChromaDB OK", file=sys.stderr)
    except Exception as e:
        status["chromadb"] = f"error: {e}"

    # 2. SQLite確認
    from database import get_session
    try:
        print("Checking SQLite...", file=sys.stderr)
        session = get_session()
        from sqlalchemy import text
        session.execute(text("SELECT 1"))
        session.close()
        status["sqlite"] = "ok"
        print("SQLite OK", file=sys.stderr)
    except Exception as e:
        status["sqlite"] = f"error: {e}"

    # 3. Gemini API確認（軽量リクエスト）
    try:
        print("Checking Gemini API...", file=sys.stderr)
        from gemini_client import get_client
        from config import EMBEDDING_MODEL
        client = get_client()
        client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents='ping'
        )
        status["gemini_api"] = "ok"
        print("Gemini API OK", file=sys.stderr)
    except Exception as e:
        status["gemini_api"] = f"error: {e}"

    # 4. Google Drive認証確認
    try:
        print("Checking Google Drive...", file=sys.stderr)
        from drive_sync import get_auth_status
        drive_info = get_auth_status()
        if drive_info.get("authenticated"):
            expires_h = drive_info.get("expires_in_hours")
            expires_str = f", expires_in={expires_h}h" if expires_h is not None else ""
            status["google_drive"] = f"ok{expires_str}"
        else:
            status["google_drive"] = f"not authenticated: {drive_info.get('message', '')}"
        print("Google Drive OK", file=sys.stderr)
    except Exception as e:
        status["google_drive"] = f"error: {e}"

    # 5. ファイルストレージ確認
    try:
        print("Checking File Storage...", file=sys.stderr)
        from indexer import scan_files
        files = scan_files()
        status["file_storage"] = f"ok ({len(files)} files)"
        print("File Storage OK", file=sys.stderr)
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
        "timestamp": _dt.now().isoformat(),
    }

    all_ok = overall == "ok"
    return JSONResponse(
        content=result,
        status_code=200 if all_ok or overall == "degraded" else 503
    )

@router.get("/api/stats", response_model=StatsResponse)
def get_stats():
    """データベース統計を取得"""
    from retriever import get_db_stats
    stats = get_db_stats()
    return StatsResponse(
        file_count=stats["file_count"],
        chunk_count=stats["chunk_count"],
        last_updated=stats["last_updated"],  # Optional[str] allows None
    )

@router.get("/api/ocr/status")
def get_ocr_status():
    """OCR処理中・最近処理したファイルのステータスを返す。
    
    UI 改善: LegacyDocument の status に加えて DocumentVersion.ingest_status も参照し、
    パイプライン全ステージ（OCR→分類→Drive同期→インデックス→完了）の状態を返す。
    """
    try:
        from database import get_session, LegacyDocument, DocumentVersion
        from sqlalchemy import or_
        session = get_session()
        try:
            from datetime import datetime, timedelta
            recent_cutoff = datetime.now() - timedelta(minutes=30)

            # アクティブなステータス（時間制限なし）
            ACTIVE_STATUSES = [
                "processing", "ocr_completed",
                "uploading_to_drive", "drive_synced",
                "enriched", "indexing",
                "enrichment_failed",   # エラー系もアクティブ扱い
            ]

            docs = session.query(LegacyDocument).filter(
                or_(
                    LegacyDocument.status.in_(ACTIVE_STATUSES),
                    # failed/completed は30分以内のみ
                    (LegacyDocument.status == "failed")    & (LegacyDocument.updated_at >= recent_cutoff),
                    (LegacyDocument.status == "completed") & (LegacyDocument.updated_at >= recent_cutoff),
                )
            ).order_by(LegacyDocument.updated_at.desc()).limit(20).all()

            jobs = []
            for doc in docs:
                # DocumentVersion から詳細ステージを補完
                ingest_status = doc.status
                error_message = doc.error_message
                if doc.source_pdf_hash:
                    dv = session.query(DocumentVersion).filter(
                        DocumentVersion.version_hash == doc.source_pdf_hash
                    ).first()
                    if dv:
                        # ingest_status が LegacyDocument より詳細な場合は優先
                        if dv.ingest_status not in (None, "accepted", "searchable"):
                            ingest_status = dv.ingest_status
                        if dv.error_message and not error_message:
                            error_message = dv.error_message

                jobs.append({
                    "file_path":          doc.file_path,
                    "filename":           doc.filename,
                    "status":             ingest_status,
                    "processed_pages":    doc.processed_pages or 0,
                    "total_pages":        doc.total_pages or 1,
                    "error_message":      error_message,
                    "estimated_remaining":doc.estimated_remaining,
                    "updated_at":         doc.updated_at.isoformat() if doc.updated_at else None,
                })

            # processing_count = アクティブ（完了・エラー以外）の数
            active_statuses_set = set(ACTIVE_STATUSES) | {"processing"}
            processing_count = sum(
                1 for j in jobs
                if j["status"] in active_statuses_set
                and j["status"] not in ("enrichment_failed", "failed")
            )
            return {
                "processing_count": processing_count,
                "jobs": jobs
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to get OCR status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="OCR status retrieval failed")

@router.delete("/api/ocr/status/{file_path:path}")
def dismiss_ocr_status(file_path: str):
    """OCRステータスエントリを削除（非表示化）"""
    try:
        from database import get_session, LegacyDocument, DocumentVersion
        session = get_session()
        try:
            # Bug fix: 旧実装は DocumentVersion.id に file_path を LIKE マッチしており
            # LegacyDocument が更新されなかった。
            # 正しく LegacyDocument.file_path で直接検索して dismissed に更新する。
            legacy = session.query(LegacyDocument).filter(
                LegacyDocument.file_path == file_path
            ).first()
            if legacy:
                legacy.status = "dismissed"
                from datetime import datetime
                legacy.updated_at = datetime.now()

                # 新モデル側も合わせて更新
                if legacy.source_pdf_hash:
                    doc_ver = session.query(DocumentVersion).filter(
                        DocumentVersion.version_hash == legacy.source_pdf_hash
                    ).first()
                    if doc_ver:
                        doc_ver.ingest_status = "dismissed"
                        doc_ver.updated_at = datetime.now()

            session.commit()
        finally:
            session.close()
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to dismiss OCR status for {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to dismiss OCR status")

@router.post("/api/index", response_model=IndexResponse)
def rebuild_index(force: bool = False):
    """インデックスを再構築"""
    try:
        from indexer import build_index
        stats = build_index(force_rebuild=force)
        return IndexResponse(**stats)
    except Exception as e:
        logger.error(f"Failed to rebuild index: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Index rebuild failed")

@router.get("/api/system/export-source")
async def export_source():
    """ソースコード一式をZIPでダウンロード"""
    try:
        import zipfile
        from io import BytesIO
        from datetime import datetime
        
        EXCLUDE_DIRS = {
            'node_modules', 'venv', '.git', '__pycache__', 
            'knowledge_base', 'chroma_db', '.next', '.idea', '.vscode',
            'brain', '.gemini', 'artifacts'
        }
        EXCLUDE_FILES = {
            '.DS_Store', 'ocr_progress.json', 'file_index.json', 'credentials.json'
        }
        
        zip_buffer = BytesIO()
        # routers ディレクトリの親をベースディレクトリにする
        base_dir = Path(__file__).parent.parent.resolve()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(base_dir):
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
        
        return StreamingResponse(
            iter([zip_buffer.getvalue()]), 
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Source export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed")

# ========== 設定関連 ==========

@router.get("/api/settings/gemini-key")
async def get_gemini_key():
    """設定済みのGemini APIキーを取得（セキュリティのため一部隠蔽）"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"api_key": "", "configured": False}
    
    if len(api_key) > 8:
        masked = f"{api_key[:4]}...{api_key[-4:]}"
    else:
        masked = "****"
        
    return {"api_key": masked, "configured": True}

@router.post("/api/settings/gemini-key")
async def set_gemini_key(request: GeminiKeyRequest):
    """Gemini APIキーを設定・保存"""
    new_key = request.api_key.strip()
    if not new_key:
        raise HTTPException(status_code=400, detail="APIキーが空です")
    
    env_path = Path(__file__).parent.parent / ".env"
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
        
    os.environ["GEMINI_API_KEY"] = new_key
    import config
    config.GEMINI_API_KEY = new_key
    
    import gemini_client as _gc
    _gc.reconfigure(new_key)

    return {"message": "APIキーを保存しました"}

@router.post("/api/settings/test-gemini")
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
            model="gemini-3-flash-preview",
            contents="Hello, this is a connection test.",
        )
        return {"success": True, "message": "接続テスト成功", "response": _response.text[:50]}
    except Exception as e:
        logger.error(f"Gemini API test failed: {e}", exc_info=True)
        return {"success": False, "message": f"接続テスト失敗: {str(e)}"}

# ========== Layer 0 管理 ==========

@router.get("/api/system/layer0")
async def get_layer0():
    """現在のLayer 0プロンプトの内容を返す"""
    from generator import _LAYER0_PATH, _layer0_cache
    return {
        "content": _layer0_cache,
        "filename": _LAYER0_PATH.name,
        "filepath": str(_LAYER0_PATH),
        "file_exists": _LAYER0_PATH.exists(),
        "char_count": len(_layer0_cache),
    }

class Layer0TextRequest(BaseModel):
    content: str

@router.post("/api/system/layer0/text")
async def update_layer0_text(req: Layer0TextRequest):
    """テキストをLayer 0ファイルに書き込み、キャッシュを更新する"""
    from generator import _LAYER0_PATH, reload_layer0
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content が空です")
    try:
        _LAYER0_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LAYER0_PATH.write_text(req.content.strip(), encoding="utf-8")
        new_content = reload_layer0()
        logger.info(f"Layer 0 updated via text API. chars={len(new_content)}")
        return {"message": "Layer 0を更新しました", "char_count": len(new_content)}
    except Exception as e:
        logger.error(f"Layer 0 text update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/system/layer0/upload")
async def upload_layer0_file(file: UploadFile = File(...)):
    """MDまたはTXTファイルをLayer 0としてアップロードし、キャッシュを更新する"""
    from generator import _LAYER0_PATH, reload_layer0
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".md", ".txt"):
        raise HTTPException(status_code=400, detail=".md または .txt ファイルのみ対応しています")
    try:
        content = (await file.read()).decode("utf-8").strip()
        if not content:
            raise HTTPException(status_code=400, detail="ファイルが空です")
        _LAYER0_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LAYER0_PATH.write_text(content, encoding="utf-8")
        new_content = reload_layer0()
        logger.info(f"Layer 0 uploaded. filename={file.filename}, chars={len(new_content)}")
        return {"message": f"{file.filename} をLayer 0として適用しました", "char_count": len(new_content)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Layer 0 upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/system/layer0/reload")
async def reload_layer0_endpoint():
    """ディスク上のLayer 0ファイルをキャッシュに再読み込みする"""
    from generator import reload_layer0
    try:
        new_content = reload_layer0()
        return {"message": "Layer 0を再読み込みしました", "char_count": len(new_content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
