"""
multi_index_searcher.py - マルチモーダル マルチインデックス検索

全モダリティの ChromaDB コレクション（テキスト・ビジュアル・音声・動画・インターリーブ）を
並行検索し、結果を返す。

RRF (Reciprocal Rank Fusion) によるスコア統合は reranker.py で行う。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from config import (
    CHROMA_DB_DIR,
    COLLECTION_NAME,
    VISUAL_VECTORS_COLLECTION,
    AUDIO_VECTORS_COLLECTION,
    VIDEO_VECTORS_COLLECTION,
    MIXED_VECTORS_COLLECTION,
)
from dense_indexer import get_chroma_client
from embedding_client import GeminiEmbedding2Client

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """単一検索ヒット。"""
    chunk_id: str
    score: float              # 距離ベースのスコア（小さいほど類似）→ 1-distance に変換
    collection: str
    metadata: dict[str, Any] = field(default_factory=dict)
    document: Optional[str] = None  # テキストコレクションのみ


def _chroma_query(collection, query_embedding: list[float], top_k: int) -> list[SearchResult]:
    """ChromaDB コレクションを同期クエリし、SearchResult リストを返す。"""
    try:
        res = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["metadatas", "distances", "documents"],
        )
    except Exception as e:
        logger.warning(f"[MultiIndexSearcher] Query failed for {collection.name}: {e}")
        return []

    results = []
    ids = res.get("ids", [[]])[0]
    distances = res.get("distances", [[]])[0]
    metadatas = res.get("metadatas", [[]])[0]
    documents = res.get("documents", [[None]])[0] if res.get("documents") else [None] * len(ids)

    for chunk_id, dist, meta, doc in zip(ids, distances, metadatas, documents):
        # cosine distance (0–2) を similarity score (0–1) に変換
        score = 1.0 - (dist / 2.0)
        results.append(SearchResult(
            chunk_id=chunk_id,
            score=score,
            collection=collection.name,
            metadata=meta or {},
            document=doc,
        ))

    return results


class MultiIndexSearcher:
    """
    全モダリティコレクションを並行検索するクラス。

    使用例:
        searcher = MultiIndexSearcher()
        results = await searcher.search("1階平面図を見せて", top_k=20)
    """

    ALL_COLLECTIONS = [
        COLLECTION_NAME,
        VISUAL_VECTORS_COLLECTION,
        AUDIO_VECTORS_COLLECTION,
        VIDEO_VECTORS_COLLECTION,
        MIXED_VECTORS_COLLECTION,
    ]

    def __init__(self):
        chroma = get_chroma_client(CHROMA_DB_DIR)
        self._collections = {}
        for name in self.ALL_COLLECTIONS:
            try:
                self._collections[name] = chroma.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e:
                logger.warning(f"[MultiIndexSearcher] Could not load collection '{name}': {e}")

        self.embed_client = GeminiEmbedding2Client()

    async def search(
        self,
        query: str,
        top_k: int = 20,
        collections: Optional[list[str]] = None,
    ) -> dict[str, list[SearchResult]]:
        """
        クエリを埋め込み、指定コレクション（省略時は全コレクション）を並行検索する。

        重要: 既存の architectural_knowledge コレクションは gemini-embedding-001 (768次元) で
        インデックスされているため、旧来の埋め込み関数を使用して互換性を維持する。
        新コレクション (visual/audio/video/mixed) は gemini-embedding-2-preview (3072次元) を使用。

        Returns:
            {collection_name: [SearchResult, ...]} の辞書
        """
        target_collections = collections or list(self._collections.keys())
        active = {k: v for k, v in self._collections.items() if k in target_collections}

        # テキストコレクションと新コレクションで埋め込みモデルを分ける
        new_collections = {
            k: v for k, v in active.items() if k != COLLECTION_NAME
        }
        has_text_collection = COLLECTION_NAME in active

        # 新コレクション用: gemini-embedding-2-preview で埋め込み
        v2_embedding: Optional[list[float]] = None
        if new_collections:
            v2_embedding = await self.embed_client.embed_text(
                query, task_type="RETRIEVAL_QUERY"
            )

        # テキストコレクション用: 既存の gemini-embedding-001 で埋め込み（次元互換性維持）
        legacy_embedding: Optional[list[float]] = None
        if has_text_collection:
            try:
                from indexer import get_query_embedding as _legacy_embed
                legacy_embedding = await asyncio.to_thread(_legacy_embed, query)
            except Exception as e:
                logger.warning(f"[MultiIndexSearcher] Legacy embedding failed: {e}; skipping text collection")
                has_text_collection = False

        # 並行クエリを組み立てる
        tasks: dict[str, any] = {}
        if has_text_collection and legacy_embedding is not None:
            tasks[COLLECTION_NAME] = asyncio.to_thread(
                _chroma_query, active[COLLECTION_NAME], legacy_embedding, top_k
            )
        for name, col in new_collections.items():
            if v2_embedding is not None:
                tasks[name] = asyncio.to_thread(_chroma_query, col, v2_embedding, top_k)

        results: dict[str, list[SearchResult]] = {}
        for name, coro in tasks.items():
            try:
                results[name] = await coro
            except Exception as e:
                logger.warning(f"[MultiIndexSearcher] Collection '{name}' query error: {e}")
                results[name] = []

        total = sum(len(v) for v in results.values())
        logger.info(
            f"[MultiIndexSearcher] query={query!r:.50} top_k={top_k} "
            f"collections={list(results.keys())} total_hits={total}"
        )
        return results

    async def expand_context(
        self,
        hit: SearchResult,
        window: int = 1,
    ) -> list[SearchResult]:
        """
        ヒットした結果の前後コンテキストを取得する（親チャンク展開）。

        - visual: ±window ページ
        - audio:  ±window チャンク
        - video:  ±window セグメント
        - text:   現状そのまま返す
        """
        vector_type = hit.metadata.get("vector_type", "")
        source_id = hit.metadata.get("source_id", "")
        version_id = hit.metadata.get("version_id", "")

        if not source_id or vector_type not in ("visual", "audio", "video", "interleaved"):
            return [hit]

        col = self._collections.get(hit.collection)
        if col is None:
            return [hit]

        if vector_type == "visual":
            page = hit.metadata.get("page_number", 1)
            pages = list(range(max(1, page - window), page + window + 1))
            return await asyncio.to_thread(
                self._fetch_by_pages, col, source_id, pages
            )
        elif vector_type in ("audio",):
            idx = hit.metadata.get("chunk_index", 0)
            indices = list(range(max(0, idx - window), idx + window + 1))
            return await asyncio.to_thread(
                self._fetch_by_chunk_indices, col, source_id, indices, "chunk_index"
            )
        elif vector_type == "video":
            idx = hit.metadata.get("segment_index", 0)
            indices = list(range(max(0, idx - window), idx + window + 1))
            return await asyncio.to_thread(
                self._fetch_by_chunk_indices, col, source_id, indices, "segment_index"
            )

        return [hit]

    def _fetch_by_pages(
        self, col, source_id: str, pages: list[int]
    ) -> list[SearchResult]:
        results = []
        for page in pages:
            try:
                res = col.get(
                    where={"$and": [{"source_id": source_id}, {"page_number": page}]},
                    include=["metadatas", "documents"],
                )
                for chunk_id, meta in zip(res["ids"], res["metadatas"]):
                    results.append(SearchResult(
                        chunk_id=chunk_id, score=0.0,
                        collection=col.name, metadata=meta or {},
                    ))
            except Exception as e:
                logger.debug(f"[MultiIndexSearcher] expand_context page={page}: {e}")
        return results

    def _fetch_by_chunk_indices(
        self, col, source_id: str, indices: list[int], index_key: str
    ) -> list[SearchResult]:
        results = []
        for idx in indices:
            try:
                res = col.get(
                    where={"$and": [{"source_id": source_id}, {index_key: idx}]},
                    include=["metadatas"],
                )
                for chunk_id, meta in zip(res["ids"], res["metadatas"]):
                    results.append(SearchResult(
                        chunk_id=chunk_id, score=0.0,
                        collection=col.name, metadata=meta or {},
                    ))
            except Exception as e:
                logger.debug(f"[MultiIndexSearcher] expand_context {index_key}={idx}: {e}")
        return results
