# retriever.py - ベクトル検索・コンテキスト構築（Webアプリ版）

import os
import json
from typing import List, Dict, Any, Optional
from collections import Counter

import chromadb

from config import (
    CHROMA_DB_DIR,
    FILE_INDEX_PATH,
    TOP_K_RESULTS,
    COLLECTION_NAME,
)
from indexer import GeminiEmbeddingFunction, get_query_embedding


def get_collection():
    """ChromaDBコレクションを取得"""
    if not os.path.exists(CHROMA_DB_DIR):
        os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    
    client = chromadb.PersistentClient(
        path=CHROMA_DB_DIR,
        settings=chromadb.config.Settings(anonymized_telemetry=False)
    )
    embedding_function = GeminiEmbeddingFunction()
    
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )


def search(
    query: str,
    n_results: int = TOP_K_RESULTS,
    filter_category: Optional[str] = None,
    filter_file_type: Optional[str] = None,
    filter_date_range: Optional[str] = None,
    filter_tags: Optional[List[str]] = None,
    tag_match_mode: str = "any",
) -> Dict[str, Any]:
    """ハイブリッド検索（ベクトル検索 + キーワードリランク）を実行"""
    collection = get_collection()
    
    # コレクションが空の場合
    if collection.count() == 0:
        return {"documents": [], "metadatas": [], "distances": []}
    
    query_embedding = get_query_embedding(query)
    
    # フィルタ条件の構築
    where_conditions = []
    
    if filter_category:
        where_conditions.append({"category": filter_category})
        
    if filter_file_type:
        # ドットを除去して拡張子のみにする (.pdf -> pdf)
        ext = filter_file_type.lstrip('.').lower()
        where_conditions.append({"file_type": ext})
        
    if filter_date_range:
        from datetime import datetime, timedelta
        now = datetime.now()
        start_date = None
        
        if filter_date_range == '7d':
             start_date = now - timedelta(days=7)
        elif filter_date_range == '1m':
             start_date = now - timedelta(days=30)
        elif filter_date_range == '3m':
             start_date = now - timedelta(days=90)
             
        if start_date:
            # modified_at は ISOフォーマット文字列
            # ChromaDBの比較演算子: $gte (greater than or equal)
            where_conditions.append({"modified_at": {"$gte": start_date.isoformat()}})
            
    if filter_calendar_date_range: # (Renamed variable in my head, but user used filter_date_range)
         pass # (Keep existing date logic)
         
    # ... keeping existing date logic variable name ...
    
    if filter_tags:
        tag_conditions = [{"tags_str": {"$contains": tag}} for tag in filter_tags]
        if tag_match_mode == "all":
            # AND検索
            if len(tag_conditions) == 1:
                where_conditions.append(tag_conditions[0])
            else:
                where_conditions.append({"$and": tag_conditions})
        else:
            # OR検索 (Default: any)
            if len(tag_conditions) == 1:
                where_conditions.append(tag_conditions[0])
            else:
                where_conditions.append({"$or": tag_conditions})

    where_filter = None
    if len(where_conditions) == 1:
        where_filter = where_conditions[0]
    elif len(where_conditions) > 1:
        where_filter = {"$and": where_conditions}
    
    # 1. ベクトル検索（候補を多めに取得）
    candidate_k = n_results * 3
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=candidate_k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )
    
    if not results["documents"] or not results["documents"][0]:
        return {"documents": [], "metadatas": [], "distances": []}

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]
    
    # 2. キーワードスコアリング (簡易実装)
    import re
    keywords = list(set(re.findall(r'\w+', query.lower())))
    
    scored_results = []
    
    # ベクトルスコアの正規化用
    max_dist = max(dists) if dists else 1.0
    min_dist = min(dists) if dists else 0.0
    dist_range = max_dist - min_dist if max_dist > min_dist else 1.0
    
    for doc, meta, dist in zip(docs, metas, dists):
        # ベクトルスコア (距離が小さいほど類似度が高い -> 1.0に近いほど良いように変換)
        # Cosine distanceの場合: 0(一致) ~ 2(反対)
        # ここでは単純に正規化して反転
        vector_score = 1.0 - ((dist - min_dist) / dist_range)
        
        # キーワードスコア
        doc_lower = doc.lower()
        keyword_score = 0
        for kw in keywords:
            # 単純な出現頻度ではなく、存在するかどうか + 頻度対数などを考慮すべきだが
            # ここでは出現数 * 重み
            count = doc_lower.count(kw)
            if count > 0:
                keyword_score += 1.0 + (0.1 * count) # 基礎点 + 頻度ボーナス
        
        # 統合スコア (ベクトル:キーワード = 7:3 くらい？)
        # キーワードが全く含まれない場合はベクトルスコアのみ
        final_score = (vector_score * 0.7) + (min(keyword_score, 3.0) * 0.3)
        
        scored_results.append({
            "doc": doc,
            "meta": meta,
            "dist": dist,
            "score": final_score
        })
    
    # 3. リランク
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    
    # 上位K件を返す
    top_results = scored_results[:n_results]
    
    return {
        "documents": [r["doc"] for r in top_results],
        "metadatas": [r["meta"] for r in top_results],
        "distances": [r["dist"] for r in top_results],
    }


def build_context(search_results: Dict[str, Any]) -> str:
    """検索結果からLLMに渡すコンテキストを構築"""
    context_parts = []
    
    documents = search_results.get("documents", [])
    metadatas = search_results.get("metadatas", [])
    
    for doc, meta in zip(documents, metadatas):
        filename = meta.get("filename", "不明")
        category = meta.get("category", "")
        subcategory = meta.get("subcategory", "")
        sub_subcategory = meta.get("sub_subcategory", "")
        page_number = meta.get("page_number")
        
        category_path = " > ".join(filter(None, [category, subcategory, sub_subcategory]))
        page_info = f" (p.{page_number})" if page_number else ""
        
        context_parts.append(
            f"=== 出典: {filename}{page_info}（カテゴリ: {category_path}）===\n{doc}"
        )
    
    return "\n\n".join(context_parts)


def get_source_files(search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """検索結果からユニークなソースファイル一覧を取得（ページ情報含む）"""
    metadatas = search_results.get("metadatas", [])
    
    file_counter = Counter()
    file_info_map = {}
    file_pages_map = {} # rel_path -> set(page_numbers)
    
    for meta in metadatas:
        rel_path = meta.get("rel_path", "")
        if not rel_path:
            continue
        
        file_counter[rel_path] += 1
        
        # ページ番号収集
        page_num = meta.get("page_number")
        if rel_path not in file_pages_map:
            file_pages_map[rel_path] = set()
        if page_num is not None:
            file_pages_map[rel_path].add(int(page_num))
        
        if rel_path not in file_info_map:
            category = meta.get("category", "")
            subcategory = meta.get("subcategory", "")
            sub_subcategory = meta.get("sub_subcategory", "")
            category_path = " > ".join(filter(None, [category, subcategory, sub_subcategory]))
            
            file_info_map[rel_path] = {
                "filename": meta.get("filename", "不明"),
                "rel_path": rel_path,
                "category": category_path,
                "category": category_path,
                "source_pdf": meta.get("source_pdf"),
                "tags": meta.get("tags_str", "").split(",") if meta.get("tags_str") else [],
            }
    
    source_files = []
    for rel_path, count in file_counter.most_common():
        info = file_info_map[rel_path].copy()
        info["relevance_count"] = count
        # ページリストをソートして追加
        pages = sorted(list(file_pages_map.get(rel_path, [])))
        info["pages"] = pages
        source_files.append(info)
    
    return source_files


def get_db_stats() -> Dict[str, Any]:
    """ChromaDBの統計情報を取得"""
    try:
        collection = get_collection()
        count = collection.count()
        
        # DBからファイル数と最終更新時刻を取得
        from database import get_session, Document as DbDocument
        session = get_session()
        try:
            file_count = session.query(DbDocument).filter(
                DbDocument.file_hash.isnot(None)
            ).count()
            
            from sqlalchemy import func
            latest = session.query(
                func.max(DbDocument.last_indexed_at)
            ).scalar()
            last_updated = latest.isoformat() if latest else "未インデックス"
        finally:
            session.close()
        
        return {
            "chunk_count": count,
            "file_count": file_count,
            "last_updated": last_updated,
        }
    except Exception as e:
        return {
            "chunk_count": 0,
            "file_count": 0,
            "last_updated": "エラー",
            "error": str(e),
        }


def _load_file_index() -> Dict[str, Any]:
    """DBからファイルインデックスを読み込み（後方互換の辞書形式）"""
    from database import get_session, Document as DbDocument
    session = get_session()
    try:
        docs = session.query(DbDocument).filter(
            DbDocument.file_hash.isnot(None)
        ).all()
        files = {}
        for doc in docs:
            files[doc.file_path] = {
                "hash": doc.file_hash,
                "chunk_count": doc.chunk_count or 0,
            }
        return {"files": files}
    finally:
        session.close()
