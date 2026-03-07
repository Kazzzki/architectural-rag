import logging
from typing import List

logger = logging.getLogger(__name__)

def calculate_recency_score(last_used_at_iso: str, created_at_iso: str) -> float:
    from datetime import datetime
    try:
        if last_used_at_iso:
            dt = datetime.fromisoformat(last_used_at_iso)
        elif created_at_iso:
            dt = datetime.fromisoformat(created_at_iso)
        else:
            return 0.5
            
        now = datetime.now()
        age_days = (now - dt).days
        # Sigmoid decay
        score = max(0.0, 1.0 - (age_days / 365.0))
        return score
    except Exception:
        return 0.5

def rerank_results(items: List[dict], semantic_distances: List[float], max_items: int = 15) -> List[dict]:
    """
    抽出された結果をリランクする。
    items: [{ "id": "...", "metadata": { ... }, "document": "..." }, ...]
    """
    ranked = []
    
    for i, item in enumerate(items):
        meta = item.get("metadata", {})
        
        # distance は小さいほど類似度が高いと仮定し score化 (cosine距離が使われている場合)
        dist = semantic_distances[i] if i < len(semantic_distances) else 1.0
        semantic_score = max(0.0, 1.0 - dist)
        
        salience = float(meta.get("salience", 0.0))
        confidence = float(meta.get("confidence", 0.5))
        utility_score = float(meta.get("utility_score", 0.5))
        
        recency = calculate_recency_score(meta.get("last_used_at", ""), meta.get("created_at", ""))
        usage_score = min(float(meta.get("support_count", 1)) / 10.0, 1.0) # 簡易

        final_score = (
            0.45 * semantic_score +
            0.15 * recency +
            0.15 * salience +
            0.10 * confidence +
            0.10 * utility_score +
            0.05 * usage_score
        )
        
        # 新しい辞書を作って返す
        ranked_item = item.copy()
        ranked_item["_final_score"] = final_score
        ranked.append(ranked_item)

    # 降順ソート
    ranked.sort(key=lambda x: x["_final_score"], reverse=True)
    
    # 簡易MMR的（上位から類似しすぎたものを弾くなど）な実装が望ましいが
    # 時間の都合上ここではシンプルなTop-K + 簡単な重複チェックにとどめる
    # 本格的なMMRはvector DB内部または埋め込み再計算が必要
    
    seen_texts = set()
    diverse_results = []
    
    for r in ranked:
        doc_snippet = r.get("document", "")[:50]
        if doc_snippet not in seen_texts:
            seen_texts.add(doc_snippet)
            diverse_results.append(r)
            if len(diverse_results) >= max_items:
                break

    return diverse_results
