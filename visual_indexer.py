"""
visual_indexer.py - Drawing ファイルのビジュアルベクトルインデックス登録

Drawing 分類された PDF/画像を Gemini Embedding 2 で直接ベクトル化し、
ChromaDB の visual_vectors コレクションに登録する。

- PDF: PyMuPDF (fitz) でページ単位 PNG 画像化してベクトル化
- PNG/JPG: そのままベクトル化
"""

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from config import CHROMA_DB_DIR, VISUAL_VECTORS_COLLECTION
from dense_indexer import get_chroma_client
from embedding_client import GeminiEmbedding2Client

logger = logging.getLogger(__name__)

_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class VisualIndexer:
    """Drawing ファイルをビジュアルベクトルとして ChromaDB に登録する。"""

    def __init__(self):
        self.client = get_chroma_client(CHROMA_DB_DIR)
        self.collection = self.client.get_or_create_collection(
            name=VISUAL_VECTORS_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self.embed_client = GeminiEmbedding2Client()

    async def index_file(
        self,
        file_path: str,
        source_pdf_hash: str,
        version_id: str,
        original_filename: str = "",
    ) -> int:
        """
        ファイルをインデックスする。

        Returns:
            登録したベクトル数
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        start = time.time()

        if ext == ".pdf":
            count = await self._index_pdf(path, source_pdf_hash, version_id, original_filename or path.name)
        elif ext in _IMAGE_MIME_TYPES:
            count = await self._index_image(path, source_pdf_hash, version_id, original_filename or path.name)
        else:
            logger.warning(f"[VisualIndexer] Unsupported file type: {ext} for {path}")
            return 0

        elapsed = time.time() - start
        logger.info(
            f"[VisualIndexer] Indexed {count} visual vectors for {path.name} "
            f"(version={version_id}, elapsed={elapsed:.1f}s)"
        )
        return count

    async def _index_pdf(
        self,
        path: Path,
        source_pdf_hash: str,
        version_id: str,
        original_filename: str,
    ) -> int:
        """PDF の各ページを PNG 化してベクトル登録する。"""
        doc = fitz.open(str(path))
        total_pages = doc.page_count
        logger.info(f"[VisualIndexer] PDF {original_filename}: {total_pages} pages")

        ids = []
        embeddings = []
        metadatas = []

        for page_num in range(total_pages):
            page = doc.load_page(page_num)
            # 解像度 150 DPI で PNG に変換
            mat = fitz.Matrix(150 / 72, 150 / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image_bytes = pix.tobytes("png")

            try:
                vec = await self.embed_client.embed_image(image_bytes, "image/png")
            except Exception as e:
                logger.error(
                    f"[VisualIndexer] Failed to embed page {page_num + 1} of {original_filename}: {e}"
                )
                continue

            chunk_id = str(uuid.uuid4())
            ids.append(chunk_id)
            embeddings.append(vec)
            metadatas.append({
                "source_id": source_pdf_hash,
                "vector_type": "visual",
                "page_number": page_num + 1,
                "content_type": "Drawing",
                "original_filename": original_filename,
                "version_id": version_id,
            })

        doc.close()

        if ids:
            self.collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

        return len(ids)

    async def _index_image(
        self,
        path: Path,
        source_pdf_hash: str,
        version_id: str,
        original_filename: str,
    ) -> int:
        """画像ファイルを直接ベクトル登録する。"""
        mime_type = _IMAGE_MIME_TYPES.get(path.suffix.lower(), "image/png")
        image_bytes = path.read_bytes()

        try:
            vec = await self.embed_client.embed_image(image_bytes, mime_type)
        except Exception as e:
            logger.error(f"[VisualIndexer] Failed to embed image {original_filename}: {e}")
            return 0

        chunk_id = str(uuid.uuid4())
        self.collection.upsert(
            ids=[chunk_id],
            embeddings=[vec],
            metadatas=[{
                "source_id": source_pdf_hash,
                "vector_type": "visual",
                "page_number": 1,
                "content_type": "Drawing",
                "original_filename": original_filename,
                "version_id": version_id,
            }],
        )
        return 1

    def delete_by_version(self, version_id: str):
        """指定バージョンのビジュアルベクトルを全削除する。"""
        self.collection.delete(where={"version_id": version_id})
        logger.info(f"[VisualIndexer] Deleted visual vectors for version_id={version_id}")


def index_visual_file(
    file_path: str,
    source_pdf_hash: str,
    version_id: str,
    original_filename: str = "",
) -> int:
    """同期エントリーポイント（スレッドから呼び出す用）。"""
    indexer = VisualIndexer()
    return asyncio.run(
        indexer.index_file(file_path, source_pdf_hash, version_id, original_filename)
    )
