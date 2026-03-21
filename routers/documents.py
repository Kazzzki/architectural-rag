from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Documents"])


@router.get("/api/documents")
def list_documents(
    category: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """ナレッジファイル一覧を取得"""
    try:
        from database import get_session, LegacyDocument
        from sqlalchemy import desc

        session = get_session()
        try:
            q = session.query(LegacyDocument)
            if category:
                q = q.filter(LegacyDocument.category == category)
            if file_type:
                q = q.filter(LegacyDocument.file_type == file_type)
            if status:
                q = q.filter(LegacyDocument.status == status)

            total = q.count()
            docs = q.order_by(desc(LegacyDocument.created_at)).offset(offset).limit(limit).all()

            return {
                "total": total,
                "documents": [
                    {
                        "id": doc.id,
                        "filename": doc.filename,
                        "file_path": doc.file_path,
                        "file_type": doc.file_type,
                        "file_size": doc.file_size,
                        "category": doc.category,
                        "subcategory": doc.subcategory,
                        "doc_type": doc.doc_type,
                        "status": doc.status,
                        "total_pages": doc.total_pages,
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                    }
                    for doc in docs
                ],
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to list documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve document list")


@router.get("/api/documents/{doc_id}/file")
def serve_document_file(doc_id: int):
    """ドキュメントのファイルをFileResponseで配信"""
    try:
        from database import get_session, LegacyDocument
        from config import KNOWLEDGE_BASE_DIR

        session = get_session()
        try:
            doc = session.query(LegacyDocument).filter(LegacyDocument.id == doc_id).first()
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            kb_root = Path(KNOWLEDGE_BASE_DIR).resolve()
            file_path = (kb_root / doc.file_path).resolve()

            # パストラバーサル防止
            try:
                file_path.relative_to(kb_root)
            except ValueError:
                raise HTTPException(status_code=403, detail="Access denied")

            if not file_path.exists():
                raise HTTPException(status_code=404, detail="File not found on disk")

            MIME_MAP = {
                ".pdf": "application/pdf",
                ".md": "text/markdown; charset=utf-8",
                ".txt": "text/plain; charset=utf-8",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
            }
            suffix = file_path.suffix.lower()
            media_type = MIME_MAP.get(suffix, "application/octet-stream")

            headers = {}
            if suffix == ".pdf":
                from urllib.parse import quote
                safe_name = quote(file_path.name)
                headers["Content-Disposition"] = f"inline; filename*=utf-8''{safe_name}"

            return FileResponse(str(file_path), media_type=media_type, headers=headers)
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to serve document file {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to serve file")


@router.get("/api/documents/{doc_id}")
def get_document(doc_id: int):
    """ドキュメント詳細（抽出テキスト含む）を取得"""
    try:
        from database import get_session, LegacyDocument
        from config import KNOWLEDGE_BASE_DIR

        session = get_session()
        try:
            doc = session.query(LegacyDocument).filter(LegacyDocument.id == doc_id).first()
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            kb_root = Path(KNOWLEDGE_BASE_DIR).resolve()
            content: Optional[str] = None

            if doc.file_type == "pdf":
                # PDFの場合はOCR済みMarkdownを読み込む
                file_abs = kb_root / doc.file_path
                md_path = file_abs.with_suffix(".md")
                if md_path.exists():
                    try:
                        content = md_path.read_text(encoding="utf-8")
                    except Exception:
                        content = None
            elif doc.file_type in ("md", "txt"):
                file_abs = kb_root / doc.file_path
                if file_abs.exists():
                    try:
                        content = file_abs.read_text(encoding="utf-8")
                    except Exception:
                        content = None

            return {
                "id": doc.id,
                "filename": doc.filename,
                "file_path": doc.file_path,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "category": doc.category,
                "subcategory": doc.subcategory,
                "doc_type": doc.doc_type,
                "status": doc.status,
                "total_pages": doc.total_pages,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "content": content,
                "file_url": f"/api/documents/{doc_id}/file",
            }
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve document")
