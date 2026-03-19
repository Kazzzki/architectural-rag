"""
mixed_indexer.py - Mixed コンテンツのインターリーブ埋め込みインデックス登録

Mixed 分類された PDF をページ単位で処理する。
各ページについて:
1. PyMuPDF でページを PNG 画像化
2. PyMuPDF でテキストを抽出（高速パス）
3. 画像 + テキストをインターリーブで Gemini Embedding 2 に渡して単一ベクトル生成

結果を ChromaDB の mixed_vectors コレクションに登録する。
"""

import asyncio
import logging
import time
import uuid
from pathlib import Path

import fitz  # PyMuPDF

from config import CHROMA_DB_DIR, MIXED_VECTORS_COLLECTION
from dense_indexer import get_chroma_client
from embedding_client import GeminiEmbedding2Client

logger = logging.getLogger(__name__)


class MixedIndexer:
    """Mixed コンテンツ PDF をページ単位でインターリーブ埋め込みしてベクトル登録する。"""

    def __init__(self):
        self.client = get_chroma_client(CHROMA_DB_DIR)
        self.collection = self.client.get_or_create_collection(
            name=MIXED_VECTORS_COLLECTION,
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
        Mixed PDF をインデックスする。

        Returns:
            登録したベクトル数
        """
        path = Path(file_path)
        orig_name = original_filename or path.name
        start_time = time.time()

        if path.suffix.lower() != ".pdf":
            logger.warning(f"[MixedIndexer] Only PDF is supported, got: {path.suffix}")
            return 0

        doc = fitz.open(str(path))
        total_pages = doc.page_count
        logger.info(f"[MixedIndexer] {orig_name}: {total_pages} pages")

        ids = []
        embeddings = []
        metadatas = []

        for page_num in range(total_pages):
            page = doc.load_page(page_num)

            # 1. ページを PNG 画像化（150 DPI）
            mat = fitz.Matrix(150 / 72, 150 / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image_bytes = pix.tobytes("png")

            # 2. テキスト抽出（高速パス）
            page_text = page.get_text("text").strip()

            # 3. インターリーブ埋め込み（画像 + テキスト）
            parts = [
                {"type": "image", "content": image_bytes, "mime_type": "image/png"},
            ]
            if page_text:
                parts.append({"type": "text", "content": page_text})

            try:
                vec = await self.embed_client.embed_interleaved(parts)
            except Exception as e:
                logger.error(
                    f"[MixedIndexer] Failed to embed page {page_num + 1} of {orig_name}: {e}"
                )
                continue

            chunk_id = str(uuid.uuid4())
            ids.append(chunk_id)
            embeddings.append(vec)
            metadatas.append({
                "source_id": source_pdf_hash,
                "vector_type": "interleaved",
                "page_number": page_num + 1,
                "original_filename": orig_name,
                "version_id": version_id,
                "has_text": bool(page_text),
            })

        doc.close()

        if ids:
            self.collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

        elapsed = time.time() - start_time
        logger.info(
            f"[MixedIndexer] Indexed {len(ids)} interleaved vectors for {orig_name} "
            f"(version={version_id}, elapsed={elapsed:.1f}s, dim={len(embeddings[0]) if embeddings else 0})"
        )
        return len(ids)

    def delete_by_version(self, version_id: str):
        self.collection.delete(where={"version_id": version_id})
        logger.info(f"[MixedIndexer] Deleted mixed vectors for version_id={version_id}")


def index_mixed_file(
    file_path: str,
    source_pdf_hash: str,
    version_id: str,
    original_filename: str = "",
) -> int:
    """同期エントリーポイント（スレッドから呼び出す用）。"""
    indexer = MixedIndexer()
    return asyncio.run(
        indexer.index_file(file_path, source_pdf_hash, version_id, original_filename)
    )
