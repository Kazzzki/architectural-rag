import logging
import re
from typing import List, Dict, Any
from database import find_similar_contexts

logger = logging.getLogger(__name__)

def get_relevant_personal_contexts(question: str, max_items: int = 3) -> List[Dict[str, Any]]:
    """
    質問に関連するパーソナルコンテキストをSQLiteから取得。
    """
    if not question:
        return []
        
    try:
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
