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
    if not file_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid file_id")
    
    # 1. file_storeから取得を試みる
    try:
        import file_store
        file_info = file_store.get_file(file_id)
        if file_info:
            fp = Path(file_info["current_path"])
            if fp.exists():
                return FileResponse(
                    fp, 
                    media_type="application/pdf",
                    filename=file_info.get("original_name", fp.name)
                )
    except Exception as e:
        logger.warning(f"file_store miss for {file_id}: {e}", exc_info=True)
    
    # 2. PDF_STORAGE_DIR内のID名ファイルにフォールバック
    from config import PDF_STORAGE_DIR
    target_path = Path(PDF_STORAGE_DIR) / f"{file_id}.pdf"
    if target_path.exists():
        return FileResponse(target_path, media_type="application/pdf")
    
    raise HTTPException(status_code=404, detail="PDF not found")

@router.get("/api/pdf/metadata/{file_id}")
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
        logger.error(f"PDF metadata error for {file_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read PDF metadata")
