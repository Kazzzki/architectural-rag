"""
reranker.py - Reciprocal Rank Fusion (RRF) によるマルチコレクション結果統合

複数コレクションの検索結果を RRF スコアで統合し、重複排除後に上位 n 件を返す。

RRF スコア: Σ 1/(k + rank_i)  (k=60 がデフォルト)

source_id が同一の結果は最高スコアのもののみ残す（重複排除）。
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from multi_index_searcher import SearchResult

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    results_per_collection: dict[str, list[SearchResult]],
    k: int = 60,
    top_n: int = 10,
) -> list[SearchResult]:
    """
    複数コレクションの検索結果を RRF で統合する。

    Args:
        results_per_collection: {collection_name: [SearchResult, ...]} の辞書
                                 各リストはスコア降順でソート済みを想定
        k: RRF パラメータ（デフォルト 60）
        top_n: 返す結果の最大件数

    Returns:
        RRF スコア降順の SearchResult リスト（重複排除済み）
    """
    # chunk_id → 累積 RRF スコア
    rrf_scores: dict[str, float] = defaultdict(float)
    # chunk_id → SearchResult (最初に見つかったもの)
    chunk_map: dict[str, SearchResult] = {}

    for collection_name, hits in results_per_collection.items():
        for rank, hit in enumerate(hits):  # rank は 0-indexed
            rrf_score = 1.0 / (k + rank + 1)
            rrf_scores[hit.chunk_id] += rrf_score
            if hit.chunk_id not in chunk_map:
                chunk_map[hit.chunk_id] = hit

    # source_id 単位の重複排除（同一ファイル・ページの複数ヒットを1件にまとめる）
    source_id_best: dict[str, tuple[str, float]] = {}  # source_key → (chunk_id, rrf_score)
    for chunk_id, score in rrf_scores.items():
        hit = chunk_map[chunk_id]
        meta = hit.metadata
        # source_key = source_id + ページ/チャンク番号で一意化
        vector_type = meta.get("vector_type", "text")
        if vector_type == "visual":
            source_key = f"{meta.get('source_id', '')}:page:{meta.get('page_number', '')}"
        elif vector_type == "audio":
            source_key = f"{meta.get('source_id', '')}:chunk:{meta.get('chunk_index', '')}"
        elif vector_type == "video":
            source_key = f"{meta.get('source_id', '')}:seg:{meta.get('segment_index', '')}"
        elif vector_type == "interleaved":
            source_key = f"{meta.get('source_id', '')}:page:{meta.get('page_number', '')}"
        else:
            # テキストチャンクは chunk_id をそのまま使う（すでに細かく分かれているため）
            source_key = chunk_id

        existing = source_id_best.get(source_key)
        if existing is None or score > existing[1]:
            source_id_best[source_key] = (chunk_id, score)

    # RRF スコア降順でソート
    sorted_keys = sorted(source_id_best.values(), key=lambda x: x[1], reverse=True)
    top_results = []
    for chunk_id, rrf_score in sorted_keys[:top_n]:
        hit = chunk_map[chunk_id]
        # RRF スコアを score フィールドに上書き
        top_results.append(SearchResult(
            chunk_id=hit.chunk_id,
            score=rrf_score,
            collection=hit.collection,
            metadata=hit.metadata,
            document=hit.document,
        ))

    logger.info(
        f"[RRF] Input collections={list(results_per_collection.keys())} "
        f"total_unique_chunks={len(rrf_scores)} "
        f"after_dedup={len(source_id_best)} top_n={len(top_results)}"
    )
    return top_results
