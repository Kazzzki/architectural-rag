from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["PDF"])

@router.get("/api/pdf/list")
def list_pdfs():
    """保存済みPDFの一覧を取得"""
    from database import get_session, Document as DbDocument
    session = get_session()
    try:
        docs = session.query(DbDocument).filter(
            DbDocument.file_hash.isnot(None), 
            DbDocument.file_type == "pdf"
        ).all()
        return [{"file_id": d.file_hash, "filename": d.filename} for d in docs]
    except Exception as e:
        logger.error(f"Failed to list PDFs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="PDF list retrieval failed")
    finally:
        session.close()

@router.get("/api/pdf/{file_id}")
async def get_pdf(file_id: str):
    """PDFファイルをバイナリ配信（file_storeから解決、フォールバックあり）"""
    import re
    if not re.match(r"^[a-zA-Z0-9_\-]{8,64}$", file_id):
        raise HTTPException(status_code=400, detail="Invalid file_id format")
    
    # 1. MetadataRepositoryから取得を試める
    from metadata_repository import MetadataRepository
    repo = MetadataRepository()
    from database import get_session, Artifact, DocumentVersion
    
    session = get_session()
    try:
        # file_id は source_pdf_hash (version_hash) と想定
        version = session.query(DocumentVersion).filter(DocumentVersion.version_hash == file_id).first()
        if not version:
            # フォールバック: 直接ハッシュ名で検索
            from config import PDF_STORAGE_DIR
            legacy_path = Path(PDF_STORAGE_DIR) / f"{file_id}.pdf"
            if legacy_path.exists():
                return FileResponse(legacy_path, media_type="application/pdf")
            raise HTTPException(status_code=404, detail="PDF not found (no version)")

        # Artifact (raw_file) を探す
        artifact = session.query(Artifact).filter(
            Artifact.version_id == version.id,
            Artifact.artifact_type == "raw_file"
        ).first()
        
        if not artifact:
            raise HTTPException(status_code=404, detail="PDF artifact not found")

        local_path = Path(artifact.storage_path)
        drive_id = artifact.drive_file_id
        
        # 1. ローカルに実体があるか確認 (Staging / Legacy)
        if local_path.exists():
            return FileResponse(local_path, media_type="application/pdf")
            
        # 2. キャッシュにあるか確認
        from config import PDF_CACHE_DIR
        cache_path = Path(PDF_CACHE_DIR) / f"{file_id}.pdf"
        if cache_path.exists():
            return FileResponse(cache_path, media_type="application/pdf")
            
        # 3. Google Drive から取得を試みる
        if drive_id:
            try:
                from drive_sync import get_drive_service, download_file
                service = get_drive_service()
                logger.info(f"Downloading PDF from Drive to cache: {file_id} (DriveID: {drive_id})")
                
                content = download_file(service, drive_id, f"{file_id}.pdf")
                
                # キャッシュ保存
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_path, "wb") as f:
                    f.write(content)
                    
                return FileResponse(cache_path, media_type="application/pdf")
            except Exception as e:
                logger.error(f"Failed to fetch from Drive: {e}")
                raise HTTPException(status_code=500, detail="Failed to fetch PDF from remote storage")

        raise HTTPException(status_code=404, detail="PDF source file not found locally or on Drive")
        
    finally:
        session.close()

@router.get("/api/pdf/metadata/{file_id}")
async def get_pdf_metadata(file_id: str):
    """PDFメタデータ取得"""
    import pypdf
    import re
    from config import PDF_STORAGE_DIR
    
    if not re.match(r"^[a-zA-Z0-9_\-]{8,64}$", file_id):
         raise HTTPException(status_code=400, detail="Invalid file_id format")

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
        logger.error(f"PDF metadata error for {file_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read PDF metadata")

@router.get("/api/pdf/by-path")
async def get_pdf_by_path(p: str):
    """パス指定によるPDFの配信（パストラバーサル防止措置付き）"""
    from config import KNOWLEDGE_BASE_DIR
    import urllib.parse
    
    decoded_path = urllib.parse.unquote(p)
    kb_dir = Path(KNOWLEDGE_BASE_DIR).resolve()
    target_path = (kb_dir / decoded_path).resolve()
    
    # パストラバーサル防止: KNOWLEDGE_BASE_DIR配下か検証
    try:
        target_path.relative_to(kb_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden path access")
        
    if target_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    filename = urllib.parse.quote(target_path.name)
    return FileResponse(
        target_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"}
    )
