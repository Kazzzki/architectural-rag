import logging
import re
from typing import List, Dict, Any
from database import find_similar_contexts

logger = logging.getLogger(__name__)

def get_relevant_personal_contexts(question: str, max_items: int = 3) -> List[Dict[str, Any]]:
    """
    質問に関連するパーソナルコンテキストを取得。
    v2が有効な場合は構造化コンテキスト(Core/Active/Capsule)をマージして返す。
    それ以外は旧SQLiteのLIKE検索へフォールバック。
    """
    if not question:
        return []
        
    try:
        from config import MEMORY_V2_ENABLED, MEMORY_V2_READ_ENABLED
        if MEMORY_V2_ENABLED and MEMORY_V2_READ_ENABLED:
            from layer_a.memory_retrieve import retrieve_context
            from datetime import datetime, timezone
            
            res = retrieve_context(user_id="default", query=question)
            
            combined = []
            if res.get("core_view"):
                combined.append(f"【Core Profile】\n{res['core_view']}")
            if res.get("active_view"):
                combined.append(f"【Active State】\n{res['active_view']}")
            if res.get("context_capsule"):
                combined.append(f"【Context Capsule】\n{res['context_capsule']}")
                
            if combined:
                full_text = "\n\n".join(combined)
                return [{
                    "id": "mem_v2",
                    "type": "layered_memory",
                    "content": full_text,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }]
                
        # シンプルに2文字以上の単語（漢字・カタカナ・英数字など）を抽出して検索キーワードとする
        # 簡易的な実装だが、SQLiteのLIKE検索とは相性が良い
        words = re.findall(r'[一-龠ぁ-んァ-ヶa-zA-Z0-9]{2,}', question)
        if not words:
            words = [question.strip()]
            
        contexts = find_similar_contexts(words, limit=max_items)
        
        results = []
        for ctx in contexts:
            results.append({
                "id": ctx.id,
                "type": ctx.type,
                "content": ctx.content,
                "updated_at": ctx.updated_at.isoformat() if ctx.updated_at else None
            })
            
        if results:
            logger.info(f"Personal context injected: {len(results)} entries for question '{question}'")
            
        return results
        
    except Exception as e:
        logger.warning(f"Error retrieving personal contexts (fallback to empty list): {e}")
        return []
