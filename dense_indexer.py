import logging
import os
import chromadb
from typing import List, Dict, Any, Optional
from gemini_client import get_client
from google.genai import types
from config import CHROMA_DB_DIR, COLLECTION_NAME, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

class DenseIndexer:
    """
    Phase 3: ChromaDB へのベクトルインデックス登録を管理する。
    """
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    def upsert_chunks(self, version_id: str, chunks: List[Dict[str, Any]]):
        """
        チャンクを ChromaDB に登録。内部で Gemini Embedding を取得する。
        """
        if not chunks:
            return

        leaf_chunks = [c for c in chunks if c["chunk_type"] == "leaf"]
        if not leaf_chunks:
            # Phase 3ではLeafのみインデックス対象とするか、あるいはSectionも対象にするか検討
            # ここではLeafのみをベクトル検索対象とする (アーキテクチャ設計に合わせる)
            logger.warning(f"[DenseIndexer] No leaf chunks found for {version_id}")
            return

        ids = []
        documents = []
        metadatas = []
        
        # バッチ処理
        gemini = get_client()
        
        for chunk in leaf_chunks:
            ids.append(chunk["id"])
            documents.append(chunk["content"])
            
            # メタデータの整形 (ChromaDBはネストした辞書をサポートしないため平坦化)
            meta = {
                "version_id": version_id,
                "chunk_type": chunk["chunk_type"],
            }
            if chunk.get("metadata"):
                for k, v in chunk["metadata"].items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
            metadatas.append(meta)

        # Embeddingの一括取得 (Gemini APIの制限を考慮して小分けにするのが理想だが、ここでは簡易化)
        embeddings = []
        for doc in documents:
            try:
                res = gemini.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=doc,
                    config=types.EmbedContentConfig(task_type="retrieval_document")
                )
                embeddings.append(res.embeddings[0].values)
            except Exception as e:
                logger.error(f"Embedding error: {e}")
                # 失敗した場合は None を入れるか、リトライするか。ここでは0埋め
                embeddings.append([0.0] * 768) 

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"[DenseIndexer] Indexed {len(ids)} leaf chunks into ChromaDB for {version_id}")

    def delete_by_version(self, version_id: str):
        """特定のバージョンの全チャンクを削除。"""
        self.collection.delete(where={"version_id": version_id})
