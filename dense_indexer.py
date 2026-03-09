import logging
import os
import time
import chromadb
from typing import List, Dict, Any, Optional
from gemini_client import get_client
from google.genai import types
from threading import Lock
from config import CHROMA_DB_DIR, COLLECTION_NAME, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

# --- ChromaDB Client Singleton Factory ---
_chroma_clients = {}
_chroma_lock = Lock()

def get_chroma_client(path=CHROMA_DB_DIR):
    """公開エイリアス: indexer.py / retriever.py から import されるパブリック関数"""
    return _get_chroma_client(path)

def _get_chroma_client(path=CHROMA_DB_DIR):
    """同一プロセス内で同一パスのClientを再利用するためのファクトリ"""
    with _chroma_lock:
        if path not in _chroma_clients:
            os.makedirs(path, exist_ok=True)
            _chroma_clients[path] = chromadb.PersistentClient(
                path=path,
                settings=chromadb.config.Settings(anonymized_telemetry=False)
            )
            logger.info(f"[DenseIndexer] ChromaDB client initialized for path: {path}")
        return _chroma_clients[path]


# --- Embedding バッチ処理ヘルパー ---
_EMBED_BATCH_SIZE = 20   # Gemini embedding-001 は一度に最大100件だが余裕を持って20件
_EMBED_MAX_RETRIES = 4
_EMBED_BASE_WAIT = 2.0   # 指数バックオフの基準秒数


def _embed_batch_with_retry(gemini_client, texts: List[str]) -> List[List[float]]:
    """
    テキストリストをバッチで embed_content に渡し、エンベディングを返す。
    レート制限 (429) に対して指数バックオフでリトライする。
    失敗したチャンクはゼロベクトルで埋めてパイプラインを止めない。
    """
    for attempt in range(_EMBED_MAX_RETRIES):
        try:
            res = gemini_client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(task_type="retrieval_document")
            )
            return [e.values for e in res.embeddings]
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower()
            wait = _EMBED_BASE_WAIT ** (attempt + 1)
            if attempt < _EMBED_MAX_RETRIES - 1:
                logger.warning(
                    f"[DenseIndexer] embed_content failed (attempt {attempt+1}/{_EMBED_MAX_RETRIES}): "
                    f"{type(e).__name__}: {e} — retrying in {wait:.1f}s"
                )
                time.sleep(wait)
            else:
                logger.error(
                    f"[DenseIndexer] embed_content gave up after {_EMBED_MAX_RETRIES} attempts: {e}"
                )
                # 全件ゼロベクトルで返す（パイプライン継続を優先）
                return [[0.0] * 768 for _ in texts]
    return [[0.0] * 768 for _ in texts]


class DenseIndexer:
    """
    Phase 3: ChromaDB へのベクトルインデックス登録を管理する。
    """
    def __init__(self):
        self.client = _get_chroma_client()
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    def upsert_chunks(self, version_id: str, chunks: List[Dict[str, Any]]):
        """
        チャンクを ChromaDB に登録。Gemini Embedding をバッチ取得してから upsert する。

        改善点:
        - embed_content に texts リストをまとめて渡す（バッチ処理）
        - レート制限 (429) に対して指数バックオフでリトライ
        - _EMBED_BATCH_SIZE 件ずつ分割して過大なリクエストを防ぐ
        - 失敗時はゼロベクトルでスキップ（パイプラインを止めない）
        """
        if not chunks:
            return

        leaf_chunks = [c for c in chunks if c["chunk_type"] == "leaf"]
        if not leaf_chunks:
            logger.warning(f"[DenseIndexer] No leaf chunks found for {version_id}")
            return

        ids = []
        documents = []
        metadatas = []

        for chunk in leaf_chunks:
            ids.append(chunk["id"])
            documents.append(chunk["content"])

            # メタデータ平坦化 (ChromaDB はネストした dict を受け付けない)
            meta: Dict[str, Any] = {
                "version_id": version_id,
                "chunk_type": chunk["chunk_type"],
            }
            if chunk.get("metadata"):
                for k, v in chunk["metadata"].items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
            metadatas.append(meta)

        # --- Embedding をバッチ取得 ---
        gemini = get_client()
        embeddings: List[List[float]] = []

        total = len(documents)
        for batch_start in range(0, total, _EMBED_BATCH_SIZE):
            batch_texts = documents[batch_start: batch_start + _EMBED_BATCH_SIZE]
            batch_end   = batch_start + len(batch_texts)
            logger.info(
                f"[DenseIndexer] Embedding batch {batch_start+1}–{batch_end}/{total} "
                f"for version_id={version_id}"
            )
            batch_embeddings = _embed_batch_with_retry(gemini, batch_texts)
            embeddings.extend(batch_embeddings)

            # バッチ間に短いスリープを挟んでレート制限を回避
            if batch_end < total:
                time.sleep(0.5)

        # --- ChromaDB に upsert ---
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(
            f"[DenseIndexer] Indexed {len(ids)} leaf chunks into ChromaDB for {version_id}"
        )

    def delete_by_version(self, version_id: str):
        """特定のバージョンの全チャンクを削除。"""
        self.collection.delete(where={"version_id": version_id})
