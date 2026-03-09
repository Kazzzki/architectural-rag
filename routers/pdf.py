from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["PDF"])

# ─── 重要: 静的パスを動的パス /{file_id} より先に定義する ──────────────────────
# FastAPI はルートを登録順にマッチするため、
# /api/pdf/list, /api/pdf/by-path, /api/pdf/metadata/{file_id} を先に定義しないと
# "list", "by-path", "metadata" が {file_id} として解釈されてしまう

@router.get("/api/pdf/list")
def list_pdfs():
    """保存済みPDFの一覧を取得"""
    from database import get_session, LegacyDocument
    session = get_session()
    try:
        docs = session.query(LegacyDocument).filter(
            LegacyDocument.source_pdf_hash.isnot(None),
            LegacyDocument.file_type == "pdf"
        ).all()
        return [{"file_id": d.source_pdf_hash, "filename": d.filename} for d in docs]
    except Exception as e:
        logger.error(f"Failed to list PDFs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="PDF list retrieval failed")
    finally:
        session.close()


@router.get("/api/pdf/by-path")
async def get_pdf_by_path(p: str):
    """パス指定によるPDFの配信（パストラバーサル防止措置付き）"""
    from config import KNOWLEDGE_BASE_DIR, PDF_STORAGE_DIR
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
        # PDF_STORAGE_DIR からもフォールバック検索
        storage_path = Path(PDF_STORAGE_DIR) / decoded_path
        if storage_path.exists():
            target_path = storage_path
        else:
            raise HTTPException(status_code=404, detail="File not found")

    filename = urllib.parse.quote(target_path.name)
    return FileResponse(
        target_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"}
    )


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
        # フォールバック: Artifact から解決
        from database import get_session, DocumentVersion, Artifact
        session = get_session()
        try:
            version = session.query(DocumentVersion).filter(
                DocumentVersion.version_hash == file_id
            ).first()
            if version:
                artifact = session.query(Artifact).filter(
                    Artifact.version_id == version.id,
                    Artifact.artifact_type == "raw_file"
                ).first()
                if artifact and Path(artifact.storage_path).exists():
                    target_path = Path(artifact.storage_path)
        finally:
            session.close()

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")

    try:
        reader = pypdf.PdfReader(str(target_path))
        return {
            "file_id": file_id,
            "page_count": len(reader.pages),
            "size_bytes": target_path.stat().st_size
        }
    except Exception as e:
        logger.error(f"PDF metadata error for {file_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read PDF metadata")


@router.get("/api/pdf/{file_id}")
async def get_pdf(file_id: str):
    """
    PDFファイルをバイナリ配信。
    解決順序:
      1. Artifact テーブル (raw_file) → ローカルパス
      2. PDF_STORAGE_DIR 直下の {hash}.pdf
      3. PDF_CACHE_DIR (キャッシュ)
      4. Google Drive ダウンロード → キャッシュ保存
      5. LegacyDocument.file_path から直接サーブ
    """
    import re
    if not re.match(r"^[a-zA-Z0-9_\-]{8,64}$", file_id):
        raise HTTPException(status_code=400, detail="Invalid file_id format")

    from database import get_session, Artifact, DocumentVersion, LegacyDocument
    from config import PDF_STORAGE_DIR, PDF_CACHE_DIR

    session = get_session()
    try:
        # ── 解決策1: DocumentVersion → Artifact ──────────────────────────────
        version = session.query(DocumentVersion).filter(
            DocumentVersion.version_hash == file_id
        ).first()

        if version:
            artifact = session.query(Artifact).filter(
                Artifact.version_id == version.id,
                Artifact.artifact_type == "raw_file"
            ).first()

            if artifact:
                local_path = Path(artifact.storage_path)
                drive_id = artifact.drive_file_id

                # ローカルに実体あり
                if local_path.exists():
                    return FileResponse(local_path, media_type="application/pdf")

                # キャッシュ確認
                cache_path = Path(PDF_CACHE_DIR) / f"{file_id}.pdf"
                if cache_path.exists():
                    return FileResponse(cache_path, media_type="application/pdf")

                # Google Drive からダウンロード
                if drive_id:
                    try:
                        from drive_sync import get_drive_service, download_file
                        service = get_drive_service()
                        logger.info(f"Downloading PDF from Drive: {file_id} (DriveID: {drive_id})")
                        content = download_file(service, drive_id, f"{file_id}.pdf")
                        cache_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(cache_path, "wb") as f:
                            f.write(content)
                        return FileResponse(cache_path, media_type="application/pdf")
                    except Exception as e:
                        logger.error(f"Drive download failed for {file_id}: {e}")
                        # Drive 失敗はフォールバックに任せる

        # ── 解決策2: PDF_STORAGE_DIR 直下のハッシュ名ファイル ──────────────
        legacy_path = Path(PDF_STORAGE_DIR) / f"{file_id}.pdf"
        if legacy_path.exists():
            return FileResponse(legacy_path, media_type="application/pdf")

        # ── 解決策3: LegacyDocument から file_path を直接検索 ────────────────
        # source_pdf_hash = file_id で登録されているケース
        legacy_doc = session.query(LegacyDocument).filter(
            LegacyDocument.source_pdf_hash == file_id
        ).first()
        if legacy_doc and legacy_doc.file_path:
            legacy_doc_path = Path(legacy_doc.file_path)
            if legacy_doc_path.exists():
                return FileResponse(legacy_doc_path, media_type="application/pdf")

        # ── 解決策4: file_id がそのままパスの一部になっているケース ─────────
        # (旧indexer が source_pdf_hash = sha256[:16] で登録したファイル)
        from config import KNOWLEDGE_BASE_DIR
        for search_dir in [Path(PDF_STORAGE_DIR), Path(KNOWLEDGE_BASE_DIR)]:
            for pdf_file in search_dir.rglob(f"*{file_id}*.pdf"):
                if pdf_file.exists():
                    return FileResponse(pdf_file, media_type="application/pdf")

    finally:
        session.close()

    raise HTTPException(
        status_code=404,
        detail=f"PDF not found for id={file_id}. "
               "The file may have been moved or the Drive authentication may be required."
    )
