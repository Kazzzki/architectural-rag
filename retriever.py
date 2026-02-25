# retriever.py v3 — クエリ展開・HyDE・Geminiリランク対応
#
# 変更履歴:
#   v3 (2026-02-25): クエリ意図分類・クエリ展開・HyDE・並列検索・Geminiリランク追加
#                    parent_chunk_id からの親チャンク取得に対応

import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)

import chromadb

from config import (
    CHROMA_DB_DIR,
    FILE_INDEX_PATH,
    TOP_K_RESULTS,
    COLLECTION_NAME,
)
from indexer import GeminiEmbeddingFunction, get_query_embedding, get_chroma_client, load_parent_chunk
from gemini_client import get_client
from utils.retry import sync_retry
from google.genai import types


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
    from config import GEMINI_MODEL_RAG
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

    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({
            "document":  doc,
            "metadata":  meta,
            "distance":  dist,
            "score":     1.0 - dist,  # コサイン距離を類似度スコアに変換
        })
    return hits


def _merge_hits(hits_list: List[List[Dict[str, Any]]], top_k: int = 15) -> List[Dict[str, Any]]:
    """複数検索結果をマージし、スコアが高い上位 top_k 件を返す（重複除去）"""
    dedup: Dict[str, Dict[str, Any]] = {}
    for hits in hits_list:
        for hit in hits:
            # rel_path + chunk_index でユニーク化（parent_chunk_id でも可）
            key = (hit["metadata"].get("rel_path", ""), hit["metadata"].get("chunk_index", 0))
            key_str = f"{key[0]}::{key[1]}"
            if key_str not in dedup or hit["score"] > dedup[key_str]["score"]:
                dedup[key_str] = hit
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
    from config import GEMINI_MODEL_RAG
    response = client.models.generate_content(
        model=GEMINI_MODEL_RAG,
        contents=[_RERANK_PROMPT.format(query=query, context=context[:500])],
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=8),
    )
    try:
        return float(response.text.strip())
    except ValueError:
        return 0.5


def rerank_hits(query: str, hits: List[Dict[str, Any]], threshold: float = 0.5) -> List[Dict[str, Any]]:
    """Gemini でリランクし、threshold 以上のもの上位5件を返す"""
    scored = []
    for hit in hits:
        try:
            score = _rerank_single(query, hit["document"])
        except Exception as e:
            logger.warning(f"rerank_single failed: {e}")
            score = 0.5
        if score >= threshold:
            hit = dict(hit)
            hit["rerank_score"] = score
            scored.append(hit)
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:5]


# ─── 親チャンク取得 ─────────────────────────────────────────────────────────────
def _resolve_parent_chunks(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    各チャンクの parent_chunk_id から親チャンク（500〜800文字）を取得し、
    LLM 入力用コンテキストに置き換える。
    親チャンクが取得できない場合は元の小チャンクをそのまま使用。
    """
    resolved = []
    for hit in hits:
        pid = hit["metadata"].get("parent_chunk_id", "")
        parent_text = load_parent_chunk(pid) if pid else None
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

    # ─── Step 1: クエリ意図分類・展開・HyDE ────────────────────────────────────
    doc_type_filter = None
    expanded_queries = [query]
    hypo_doc = ""

    if use_query_expansion or use_hyde:
        try:
            doc_type_filter, expanded_queries, hypo_doc = classify_and_expand(query)
        except Exception as e:
            logger.warning(f"Query expansion failed, using base query: {e}")

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
        from datetime import datetime, timedelta
        now = datetime.now()
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

    # ─── Step 2: 並列検索 ────────────────────────────────────────────────────
    all_hits_lists = []

    # 拡張クエリで検索
    if use_query_expansion:
        for eq in expanded_queries:
            hits = _search_single(eq, collection, n=n_results, where=where)
            all_hits_lists.append(hits)
    else:
        all_hits_lists.append(_search_single(query, collection, n=n_results, where=where))

    # HyDE 検索
    if use_hyde and hypo_doc:
        all_hits_lists.append(_search_single(hypo_doc, collection, n=n_results, where=where))

    # ─── Step 3: マージ ─────────────────────────────────────────────────────
    merged_hits = _merge_hits(all_hits_lists, top_k=15)

    # ─── Step 4: Gemini リランク ─────────────────────────────────────────────
    if use_rerank and merged_hits:
        try:
            final_hits = rerank_hits(query, merged_hits, threshold=0.5)
            if not final_hits:
                # リランクで全件除外された場合はリランクなし上位5件にフォールバック
                logger.warning("All hits filtered by rerank, using top-5 fallback")
                final_hits = merged_hits[:5]
        except Exception as e:
            logger.warning(f"Reranking failed, using merged hits: {e}")
            final_hits = merged_hits[:5]
    else:
        final_hits = merged_hits[:n_results]

    # ─── Step 5: 親チャンク解決 ──────────────────────────────────────────────
    final_hits = _resolve_parent_chunks(final_hits)

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
    }


# ─── コンテキスト構築 ──────────────────────────────────────────────────────────
def build_context(search_results: Dict[str, Any]) -> str:
    """
    検索結果からコンテキスト文字列を構築。
    v3 では context_text（親チャンク）を使用し、出典に source_pdf_name + page_no を明記。
    """
    hits = search_results.get("hits", [])

    if not hits:
        # 後方互換: hits がない場合は従来の documents / metadatas を使う
        documents = search_results.get("documents", [])
        metadatas = search_results.get("metadatas", [])
        if not documents:
            return ""
        context_parts = []
        for doc, meta in zip(documents, metadatas):
            source = meta.get("source_pdf_name") or meta.get("filename", "不明")
            page   = meta.get("page_no") or meta.get("page_number", "")
            page_info = f" (p.{page})" if page else ""
            cat = meta.get("category", "")
            context_parts.append(f"=== 出典: {source}{page_info}（{cat}）===\n{doc}")
        return "\n\n".join(context_parts)

    context_parts = []
    for hit in hits:
        meta = hit.get("metadata", {})
        text = hit.get("context_text") or hit.get("document", "")

        source_name = meta.get("source_pdf_name") or meta.get("filename", "不明")
        page_no     = meta.get("page_no") or meta.get("page_number", "")
        doc_type    = meta.get("doc_type", "")
        category    = meta.get("category", "")

        page_info = f" (p.{page_no})" if page_no else ""
        icon = "📐 " if doc_type == "drawing" else ""

        context_parts.append(
            f"=== {icon}出典: {source_name}{page_info}（{category}）===\n{text}"
        )

    return "\n\n".join(context_parts)


# ─── ソースファイル一覧 ─────────────────────────────────────────────────────────
def get_source_files(search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """検索結果からユニークなソースファイル一覧を取得（ページ情報含む）"""
    metadatas = search_results.get("metadatas", [])
    file_counter: Counter = Counter()
    file_info_map: Dict[str, Dict] = {}
    file_pages_map: Dict[str, set] = {}

    for meta in metadatas:
        rel_path = meta.get("rel_path", "")
        if not rel_path:
            continue
        file_counter[rel_path] += 1

        page_num = meta.get("page_no") or meta.get("page_number")
        if rel_path not in file_pages_map:
            file_pages_map[rel_path] = set()
        if page_num is not None:
            file_pages_map[rel_path].add(int(page_num))

        if rel_path not in file_info_map:
            category = meta.get("category", "")
            doc_type  = meta.get("doc_type", "")
            file_info_map[rel_path] = {
                "filename":        meta.get("filename", "不明"),
                "source_pdf_name": meta.get("source_pdf_name", meta.get("filename", "不明")),
                "source_pdf_hash": meta.get("source_pdf_hash", ""),
                "rel_path":        rel_path,
                "category":        category,
                "doc_type":        doc_type,
                "tags":            meta.get("tags_str", "").split(",") if meta.get("tags_str") else [],
            }

    source_files = []
    for rel_path, count in file_counter.most_common():
        info = file_info_map[rel_path].copy()
        info["relevance_count"] = count
        info["pages"] = sorted(file_pages_map.get(rel_path, []))
        source_files.append(info)

    return source_files


# ─── DB 統計 ─────────────────────────────────────────────────────────────────────
def get_db_stats() -> Dict[str, Any]:
    """ChromaDB と SQLite の統計情報を取得"""
    try:
        collection = get_collection()
        count = collection.count()

        from database import get_session, Document as DbDocument
        from sqlalchemy import func
        session = get_session()
        try:
            file_count = session.query(DbDocument).filter(
                DbDocument.file_hash.isnot(None)
            ).count()
            latest = session.query(func.max(DbDocument.last_indexed_at)).scalar()
            last_updated = latest.isoformat() if latest else "未インデックス"
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
            "last_updated": "エラー",
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
