"""
context_builder.py - 検索結果からLLM入力用コンテキストとソースファイル一覧を構築する

retriever.py から分離。検索ロジック(search)とコンテキスト整形(build_context, get_source_files)の
関心分離を実現する。
"""

from typing import List, Dict, Any
from collections import Counter


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

    # ページ番号ソート用キー関数
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


def get_source_files(search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """検索結果からユニークなソースファイル一覧を取得（ページ情報含む）

    戻り値スキーマ:
    {
      "source_id":       "S1",
      "filename":        str,
      "source_pdf_name": str,
      "source_pdf":      str,
      "source_pdf_hash": str,
      "rel_path":        str,
      "category":        str,
      "doc_type":        str,
      "pages":           List[int],
      "hit_count":       int,
      "relevance_count": int,
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
            source_pdf_meta = meta.get("source_pdf", "")
            source_pdf_hash = meta.get("source_pdf_hash", "")
            if not source_pdf_meta:
                if rel_path.lower().endswith(".pdf"):
                    source_pdf_meta = rel_path
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
        info["relevance_count"] = count
        info["pages"]           = sorted(list(file_pages_map.get(rel_path, set())))
        source_files.append(info)

    return source_files
