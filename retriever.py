# retriever.py v3 — クエリ展開・HyDE・Geminiリランク対応
#
# 変更履歴:
#   v3 (2026-02-25): クエリ意図分類・クエリ展開・HyDE・並列検索・Geminiリランク追加
#                    parent_chunk_id からの親チャンク取得に対応

import os
import json
import logging
import asyncio
import atexit
import concurrent.futures
from functools import lru_cache
from threading import Lock
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)

from config import (
    CHROMA_DB_DIR,
    FILE_INDEX_PATH,
    TOP_K_RESULTS,
    COLLECTION_NAME,
    RERANK_THRESHOLD,
    RERANK_CANDIDATE_COUNT,
    GEMINI_MODEL_RAG,
)
from indexer import GeminiEmbeddingFunction, get_query_embedding, load_parent_chunk
from dense_indexer import get_chroma_client
from lexical_indexer import LexicalIndexer
from gemini_client import get_client
from pipeline_metrics import MetricsTimer
from utils.retry import sync_retry
from google.genai import types

# ─── モジュールレベル ThreadPoolExecutor（リクエスト間で再利用） ─────────────────
_search_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=5, thread_name_prefix="rag_search"
)
atexit.register(lambda: _search_executor.shutdown(wait=False))

# ─── LexicalIndexer シングルトン ──────────────────────────────────────────────
_lexical_lock = Lock()
_lexical_indexer: Optional[LexicalIndexer] = None

def _get_lexical_indexer() -> LexicalIndexer:
    global _lexical_indexer
    with _lexical_lock:
        if _lexical_indexer is None:
            _lexical_indexer = LexicalIndexer()
    return _lexical_indexer

# ─── 親チャンク LRU キャッシュ ────────────────────────────────────────────────
@lru_cache(maxsize=256)
def _cached_load_parent_chunk(parent_chunk_id: str) -> Optional[str]:
    return load_parent_chunk(parent_chunk_id)


# ─── Collection ────────────────────────────────────────────────────────────────
def get_collection():
    """ChromaDB コレクションを取得"""
    client = get_chroma_client()
    embedding_function = GeminiEmbeddingFunction()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )


# ─── クエリ意図分類 + クエリ展開 ────────────────────────────────────────────────
_INTENT_SYSTEM = """あなたは建築 RAG システムのクエリアナライザーです。
ユーザーの質問を分析し、以下の JSON を返してください（日本語のみ、Markdown コードブロック不要）：

{
  "doc_type_filter": "law" | "drawing" | "spec" | "catalog" | null,
  "expanded_queries": ["拡張クエリ1", "拡張クエリ2", ...],
  "hypothetical_doc": "この質問に答える建築技術文書の一節（300文字以内）"
}

分類ルール:
- 法規・条例・基準・告示 → "law"
- 図面・納まり・詳細・平面図・断面図 → "drawing"
- 仕様・工法・施工・JASS・JIS → "spec"
- カタログ・製品・メーカー・価格 → "catalog"
- 判定できない → null

expanded_queries は建築専門用語で 3〜5 パターン生成。
hypothetical_doc は HyDE 検索用に「実際の文書の一節」として書くこと。
"""


@sync_retry(max_retries=2, base_wait=1.0)
def _call_gemini_json(prompt: str) -> Dict[str, Any]:
    """Gemini でクエリ意図分析を実行し JSON を返す"""
    client = get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL_RAG,
        contents=[
            types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        ],
        config=types.GenerateContentConfig(
            system_instruction=_INTENT_SYSTEM,
            temperature=0.1,
            max_output_tokens=1024,
        ),
    )
    text = response.text.strip()
    # コードブロックを取り除く
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def classify_and_expand(query: str) -> Tuple[Optional[str], List[str], str]:
    """
    クエリを分析して (doc_type_filter, expanded_queries, hypothetical_doc) を返す。
    Gemini 呼び出しに失敗した場合はデフォルト値を返す。
    """
    try:
        result = _call_gemini_json(query)
        doc_type_filter = result.get("doc_type_filter")
        expanded = result.get("expanded_queries", [query])
        hypo_doc  = result.get("hypothetical_doc", "")
        return doc_type_filter, expanded, hypo_doc
    except Exception as e:
        logger.warning(f"classify_and_expand failed, using fallback: {e}")
        return None, [query], ""


# ─── 単一クエリ検索 ─────────────────────────────────────────────────────────────
def _search_single(
    query_text: str,
    collection,
    n: int = TOP_K_RESULTS,
    where: Optional[Dict] = None,
    use_hyde_embedding: bool = False,
) -> List[Dict[str, Any]]:
    """単一クエリでフィルタ付きベクトル検索を実行し、ヒット一覧を返す"""
    if collection.count() == 0:
        return []

    query_embedding = get_query_embedding(query_text)

    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": n,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    try:
        results = collection.query(**kwargs)
    except Exception as e:
        logger.warning(f"ChromaDB query failed ({query_text[:40]}…): {e}")
        return []

    hits = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    # コサイン距離 > 1.0 はコサイン類似度 < 0（ほぼ無関係）なので除外
    _MAX_VECTOR_DISTANCE = 1.0
    for doc, meta, dist in zip(docs, metas, dists):
        if dist > _MAX_VECTOR_DISTANCE:
            continue
        hits.append({
            "document":  doc,
            "metadata":  meta,
            "distance":  dist,
            "score":     1.0 - dist,  # コサイン距離を類似度スコアに変換
            "search_type": "vector"
        })
    return hits

def _search_lexical(query_text: str, n: int = TOP_K_RESULTS) -> List[Dict[str, Any]]:
    """SQLite FTS5 による全文検索を実行し、ヒット一覧を返す"""
    try:
        indexer = _get_lexical_indexer()
        results = indexer.search(query_text, limit=n)
        hits = []
        for res in results:
            hits.append({
                "document": res["content"],
                "metadata": res["metadata"],
                "score": -res["score"],  # SQLite bm25 は低いほど良いため反転させる
                "search_type": "lexical"
            })
        return hits
    except Exception as e:
        logger.warning(f"Lexical search failed: {e}")
        return []


def _merge_hits(hits_list: List[List[Dict[str, Any]]], top_k: int = RERANK_CANDIDATE_COUNT) -> List[Dict[str, Any]]:
    """複数検索結果をマージし、スコアが高い上位 top_k 件を返す（重複除去）"""
    dedup: Dict[str, Dict[str, Any]] = {}
    for hits in hits_list:
        for hit in hits:
            # chunk_id があればそれ、なければ rel_path + chunk_index でユニーク化
            meta = hit.get("metadata") or {}
            chunk_id = hit.get("chunk_id") or meta.get("chunk_id")
            if not chunk_id:
                key = (meta.get("rel_path", ""), meta.get("chunk_index", 0))
                chunk_id = f"{key[0]}::{key[1]}"
            
            if chunk_id not in dedup or hit["score"] > dedup[chunk_id]["score"]:
                dedup[chunk_id] = hit
    sorted_hits = sorted(dedup.values(), key=lambda x: x["score"], reverse=True)
    return sorted_hits[:top_k]


# ─── Gemini リランク ─────────────────────────────────────────────────────────────
_RERANK_PROMPT = """以下のコンテキストはユーザーの質問に対して適切ですか？
0.0（全く関係ない）〜1.0（完全に関連）の数値のみで答えてください。

質問: {query}

コンテキスト:
{context}
"""

@sync_retry(max_retries=2, base_wait=1.0)
def _rerank_single(query: str, context: str) -> float:
    client = get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL_RAG,
        contents=[_RERANK_PROMPT.format(query=query, context=context[:1000])],
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=8),
    )
    try:
        return float(response.text.strip())
    except ValueError:
        return RERANK_THRESHOLD


def rerank_hits(query: str, hits: List[Dict[str, Any]], threshold: float = RERANK_THRESHOLD) -> List[Dict[str, Any]]:
    """Gemini でリランクし、threshold 以上のもの上位8件を返す。
    リランク評価は モジュールレベル ThreadPoolExecutor で並列化。
    """
    from concurrent.futures import as_completed

    def score_hit(hit: Dict[str, Any]):
        try:
            return _rerank_single(query, hit["document"]), hit
        except Exception as e:
            logger.warning(f"rerank_single failed: {e}")
            return RERANK_THRESHOLD, hit

    scored = []
    # リランクは per-request executor を使用（共有プールだと並行リクエスト間で
    # スレッドが奪い合いになりレイテンシが劣化するため）
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(score_hit, hit): hit for hit in hits}
        for future in as_completed(futures):
            score, hit = future.result()
            if score >= threshold:
                hit = dict(hit)
                hit["rerank_score"] = score
                scored.append(hit)

    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:8]


# ─── 親チャンク取得 ─────────────────────────────────────────────────────────────
def _resolve_parent_chunks(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    各チャンクの parent_chunk_id から親チャンク（800〜1500文字）を取得し、
    LLM 入力用コンテキストに置き換える。
    親チャンクが取得できない場合は元の小チャンクをそのまま使用。
    """
    resolved = []
    for hit in hits:
        meta = hit.get("metadata") or {}
        pid = meta.get("parent_chunk_id", "")
        parent_text = _cached_load_parent_chunk(pid) if pid else None
        hit = dict(hit)
        hit["context_text"] = parent_text if parent_text else hit["document"]
        resolved.append(hit)
    return resolved


# ─── メイン検索関数 ─────────────────────────────────────────────────────────────
def search(
    query: str,
    n_results: int = TOP_K_RESULTS,
    # 後方互換パラメータ（v2 API との互換性）
    filter_category: Optional[str] = None,
    filter_file_type: Optional[str] = None,
    filter_date_range: Optional[str] = None,
    filter_tags: Optional[List[str]] = None,
    tag_match_mode: str = "any",
    # v3 新パラメータ
    use_query_expansion: bool = True,
    use_hyde: bool = True,
    use_rerank: bool = True,
    use_lexical: bool = True,
) -> Dict[str, Any]:
    """
    v3 ハイブリッド検索:
    1. クエリ意図分類 + クエリ展開 + HyDE 仮説文書生成
    2. 各展開クエリ + HyDE で ChromaDB を並列検索
    3. スコアマージ（上位 15 件）
    4. Gemini リランク（0.5 未満除外 → 上位 5 件）
    5. parent_chunk_id から親チャンク取得
    """
    collection = get_collection()

    if collection.count() == 0:
        return {"documents": [], "metadatas": [], "distances": [], "hits": []}

    # ─── メトリクス計測 ─────────────────────────────────────────────────────
    timer = MetricsTimer()

    # ─── Step 1: クエリ意図分類・展開・HyDE ────────────────────────────────────
    doc_type_filter = None
    expanded_queries = [query]
    hypo_doc = ""

    if use_query_expansion or use_hyde:
        try:
            doc_type_filter, expanded_queries, hypo_doc = classify_and_expand(query)
        except Exception as e:
            logger.warning(f"Query expansion failed, using base query: {e}")
    timer.mark("query_expansion")

    # 後方互換フィルタが明示的に指定された場合は展開で得たフィルタより優先
    effective_doc_type_filter = filter_file_type or doc_type_filter

    # ChromaDB where 条件
    where: Optional[Dict] = None
    where_conditions = []
    if effective_doc_type_filter and effective_doc_type_filter not in ("md", "pdf"):
        where_conditions.append({"doc_type": {"$eq": effective_doc_type_filter}})
    if filter_category:
        where_conditions.append({"category": {"$eq": filter_category}})
    if filter_date_range:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        delta_map = {"7d": 7, "1m": 30, "3m": 90}
        days = delta_map.get(filter_date_range)
        if days:
            start_date = now - timedelta(days=days)
            where_conditions.append({"modified_at": {"$gte": start_date.isoformat()}})
    if filter_tags:
        tag_conds = [{"tags_str": {"$contains": t}} for t in filter_tags]
        if tag_match_mode == "all":
            where_conditions.extend(tag_conds)
        else:
            where_conditions.append({"$or": tag_conds} if len(tag_conds) > 1 else tag_conds[0])

    if len(where_conditions) == 1:
        where = where_conditions[0]
    elif len(where_conditions) > 1:
        where = {"$and": where_conditions}

    # ─── Step 2: 並列検索（モジュールレベル ThreadPoolExecutor で高速化） ──────
    from concurrent.futures import as_completed
    all_hits_lists = []

    futures = []

    # 拡張クエリで検索
    if use_query_expansion:
        for eq in expanded_queries:
            futures.append(_search_executor.submit(_search_single, eq, collection, n_results, where))
    else:
        futures.append(_search_executor.submit(_search_single, query, collection, n_results, where))

    # HyDE 検索
    if use_hyde and hypo_doc:
        futures.append(_search_executor.submit(_search_single, hypo_doc, collection, n_results, where))

    # Full-Text Search (Lexical)
    if use_lexical:
        futures.append(_search_executor.submit(_search_lexical, query, n_results))

    failed_count = 0
    for future in as_completed(futures):
        try:
            all_hits_lists.append(future.result())
        except Exception as e:
            failed_count += 1
            logger.warning(f"Parallel search task failed: {e}")

    if failed_count > 0 and not all_hits_lists:
        logger.error(f"All {failed_count} search tasks failed — returning empty results")
    timer.mark("search")

    # ─── Step 3: マージ ─────────────────────────────────────────────────────
    merged_hits = _merge_hits(all_hits_lists, top_k=RERANK_CANDIDATE_COUNT)
    timer.mark("merge")

    # ─── Step 4: Gemini リランク ─────────────────────────────────────────────
    if use_rerank and merged_hits:
        try:
            final_hits = rerank_hits(query, merged_hits, threshold=RERANK_THRESHOLD)
            if not final_hits:
                # リランクで全件除外された場合はリランクなし上位5件にフォールバック
                logger.warning("All hits filtered by rerank, using top-5 fallback")
                final_hits = merged_hits[:5]
        except Exception as e:
            logger.warning(f"Reranking failed, using merged hits: {e}")
            final_hits = merged_hits[:5]
    else:
        final_hits = merged_hits[:n_results]
    timer.mark("rerank")

    # ─── Step 5: 親チャンク解決 ──────────────────────────────────────────────
    final_hits = _resolve_parent_chunks(final_hits)
    timer.mark("parent_resolve")

    # ─── メトリクス確定 ──────────────────────────────────────────────────────
    pipeline_metrics = timer.finalize()

    # ─── 後方互換フォーマットに変換 ─────────────────────────────────────────
    documents = [h["document"] for h in final_hits]
    metadatas = [h["metadata"] for h in final_hits]
    distances = [h.get("distance", 0.0) for h in final_hits]

    return {
        "documents": documents,
        "metadatas": metadatas,
        "distances": distances,
        "hits": final_hits,  # v3 拡張フィールド（context_text を含む）
        "doc_type_filter_applied": doc_type_filter,
        "expanded_queries": expanded_queries,
        "metrics": pipeline_metrics.to_dict(),
    }


# ─── コンテキスト構築・ソースファイル一覧（context_builder.py に移動済み） ──────
# 後方互換のため re-export
from context_builder import build_context, get_source_files  # noqa: F401


# ─── DB 統計 ─────────────────────────────────────────────────────────────────────
def get_db_stats() -> Dict[str, Any]:
    """ChromaDB と SQLite の統計情報を取得"""
    try:
        collection = get_collection()
        count = collection.count()

        from database import get_session, LegacyDocument as DbLegacyDocument
        from sqlalchemy import func
        session = get_session()
        try:
            # 論理文書数 (LegacyDocument は 1ファイル = 1レコード)
            file_count = session.query(DbLegacyDocument).count()
            # 最新のインデックス完了時刻を取得
            latest = session.query(func.max(DbLegacyDocument.last_indexed_at)).scalar()
            last_updated = latest.isoformat() if latest else None
        finally:
            session.close()

        return {
            "chunk_count":  count,
            "file_count":   file_count,
            "last_updated": last_updated,
        }
    except Exception as e:
        logger.error(f"get_db_stats error: {e}", exc_info=True)
        return {
            "chunk_count":  0,
            "file_count":   0,
            "last_updated": None,
            "error":        str(e),
        }


def _load_file_index() -> Dict[str, Any]:
    """後方互換: DB からファイルインデックスを読み込み"""
    from database import get_session, Document as DbDocument
    session = get_session()
    try:
        docs = session.query(DbDocument).filter(DbDocument.file_hash.isnot(None)).all()
        files = {}
        for doc in docs:
            files[doc.file_path] = {
                "hash":        doc.file_hash,
                "chunk_count": doc.chunk_count or 0,
                "indexed_at":  doc.last_indexed_at.isoformat() if doc.last_indexed_at else None,
                "modified_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
        return files
    finally:
        session.close()
