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

from config import (
    CHROMA_DB_DIR,
    FILE_INDEX_PATH,
    TOP_K_RESULTS,
    COLLECTION_NAME,
    RERANK_THRESHOLD,
    RERANK_CANDIDATE_COUNT,
)
from indexer import GeminiEmbeddingFunction, get_query_embedding, load_parent_chunk
from dense_indexer import get_chroma_client
from lexical_indexer import LexicalIndexer
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
        indexer = LexicalIndexer()
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
    from config import GEMINI_MODEL_RAG
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
    リランク評価は ThreadPoolExecutor で並列化（1序列ループ→約N倍高速化）。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def score_hit(hit: Dict[str, Any]):
        try:
            return _rerank_single(query, hit["document"]), hit
        except Exception as e:
            logger.warning(f"rerank_single failed: {e}")
            return RERANK_THRESHOLD, hit

    scored = []
    # レートリミット配慮で max_workers=5 に制限
    with ThreadPoolExecutor(max_workers=5) as executor:
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

    # ─── Step 2: 並列検索（ThreadPoolExecutor で高速化） ─────────────────────
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_hits_lists = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []

        # 拡張クエリで検索
        if use_query_expansion:
            for eq in expanded_queries:
                futures.append(executor.submit(_search_single, eq, collection, n_results, where))
        else:
            futures.append(executor.submit(_search_single, query, collection, n_results, where))

        # HyDE 検索
        if use_hyde and hypo_doc:
            futures.append(executor.submit(_search_single, hypo_doc, collection, n_results, where))

        # Full-Text Search (Lexical)
        if use_lexical:
            futures.append(executor.submit(_search_lexical, query, n_results))

        failed_count = 0
        for future in as_completed(futures):
            try:
                all_hits_lists.append(future.result())
            except Exception as e:
                failed_count += 1
                logger.warning(f"Parallel search task failed: {e}")

        if failed_count > 0 and not all_hits_lists:
            logger.error(f"All {failed_count} search tasks failed — returning empty results")

    # ─── Step 3: マージ ─────────────────────────────────────────────────────
    merged_hits = _merge_hits(all_hits_lists, top_k=RERANK_CANDIDATE_COUNT)

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


# ─── 重複判定ヘルパー ──────────────────────────────────────────────────────────
def _is_similar(text_a: str, text_b: str, threshold: float = 0.8) -> bool:
    """先頭N文字の一致率で簡易重複判定（親チャンク800-1500文字に対応）"""
    if not text_a or not text_b:
        return False
    text_a_s = text_a.strip()
    text_b_s = text_b.strip()
    if not text_a_s or not text_b_s:
        return False
    compare_len = min(len(text_a_s), len(text_b_s), 500)
    if compare_len == 0:
        return False
    a, b = text_a_s[:compare_len], text_b_s[:compare_len]
    matches = sum(1 for ca, cb in zip(a, b) if ca == cb)
    return (matches / compare_len) >= threshold


# ─── コンテキスト構築 ──────────────────────────────────────────────────────────
def build_context(search_results: Dict[str, Any]) -> str:
    """
    検索結果からコンテキスト文字列を構築。
    v4: ドキュメント単位でグルーピング、ページ順ソート、重複除去。
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
            meta = meta or {}
            source = meta.get("source_pdf_name") or meta.get("filename", "不明")
            page   = meta.get("page_no") or meta.get("page_number", "")
            page_info = f" (p.{page})" if page else ""
            cat = meta.get("category", "")
            context_parts.append(f"=== 出典: {source}{page_info}（{cat}）===\n{doc}")
        return "\n\n".join(context_parts)

    # 1. ドキュメント単位でグルーピング
    doc_groups: Dict[str, List[Dict[str, Any]]] = {}
    for hit in hits:
        meta = hit.get("metadata") or {}
        source_key = meta.get("rel_path") or meta.get("filename", "不明")
        doc_groups.setdefault(source_key, []).append(hit)

    # ページ番号ソート用キー関数（ループ外に定義）
    def _page_sort_key(h):
        m = h.get("metadata") or {}
        p = m.get("page_no") or m.get("page_number") or 0
        try:
            return int(p)
        except (ValueError, TypeError):
            return 0

    # 2. 各グループ内でページ順ソート + 重複除去 + 結合
    context_parts = []
    for source_key, group_hits in doc_groups.items():
        group_hits.sort(key=_page_sort_key)

        # 重複除去
        seen_texts: List[str] = []
        unique_hits: List[Dict[str, Any]] = []
        for hit in group_hits:
            text = hit.get("context_text") or hit.get("document", "")
            if not any(_is_similar(text, s) for s in seen_texts):
                seen_texts.append(text)
                unique_hits.append(hit)

        if not unique_hits:
            continue

        # ヘッダー
        meta0 = unique_hits[0].get("metadata") or {}
        source_name = meta0.get("source_pdf_name") or meta0.get("filename", "不明")
        doc_type = meta0.get("doc_type", "")
        category = meta0.get("category", "")

        header = f"━━━ 出典: {source_name}（{category}/{doc_type}）━━━"

        # 各チャンクをページ単位で結合
        chunk_texts = []
        for hit in unique_hits:
            m = hit.get("metadata") or {}
            page = m.get("page_no") or m.get("page_number", "")
            text = hit.get("context_text") or hit.get("document", "")
            page_label = f"[p.{page}]" if page else ""
            chunk_texts.append(f"{page_label} {text}")

        context_parts.append(f"{header}\n" + "\n---\n".join(chunk_texts))

    return "\n\n".join(context_parts)


# ─── ソースファイル一覧 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def get_source_files(search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """検索結果からユニークなソースファイル一覧を取得（ページ情報含む）

    戻り値スキーマ:
    {
      "source_id":       "S1",          # LLMタグとの対応用（S1始まり連番）
      "filename":        str,            # チャンクのファイル名
      "source_pdf_name": str,            # 表示用PDF名
      "source_pdf":      str,            # PDFビューア用ID（空の場合あり）
      "source_pdf_hash": str,            # ハッシュベースルーティング用（空の場合あり）
      "rel_path":        str,            # ナレッジベース相対パス
      "category":        str,
      "doc_type":        str,            # "drawing" | "law" | "spec" | "catalog" | ""
      "pages":           List[int],      # 参照ページ番号（全件・昇順）
      "hit_count":       int,            # チャンクヒット数（関連度の目安）
      "relevance_count": int,            # hit_countの後方互换エイリアス
    }
    """
    metadatas = search_results.get("metadatas", [])
    file_counter: Counter = Counter()
    file_info_map: Dict[str, Dict] = {}
    file_pages_map: Dict[str, set] = {}

    for meta in metadatas:
        meta = meta or {}
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
            # source_pdf: メタデータ値 → rel_path が PDF なら rel_path をフォールバック
            source_pdf_meta = meta.get("source_pdf", "")
            source_pdf_hash = meta.get("source_pdf_hash", "")
            if not source_pdf_meta:
                if rel_path.lower().endswith(".pdf"):
                    source_pdf_meta = rel_path
                # .md の場合は空のまま（フロントがカード表示を切り替える）
            file_info_map[rel_path] = {
                "filename":        meta.get("filename", "不明"),
                "source_pdf_name": meta.get("source_pdf_name", meta.get("filename", "不明")),
                "source_pdf":      source_pdf_meta,
                "source_pdf_hash": source_pdf_hash,
                "rel_path":        rel_path,
                "category":        category,
                "doc_type":        doc_type,
                "tags":            meta.get("tags_str", "").split(",") if meta.get("tags_str") else [],
            }

    source_files = []
    for i, (rel_path, count) in enumerate(file_counter.most_common()):
        info = file_info_map[rel_path].copy()
        info["source_id"]       = f"S{i + 1}"
        info["hit_count"]       = count
        info["relevance_count"] = count  # 後方互換エイリアス
        info["pages"]           = sorted(list(file_pages_map.get(rel_path, set())))
        source_files.append(info)

    return source_files


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
