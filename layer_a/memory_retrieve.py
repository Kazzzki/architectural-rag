import logging
from typing import Dict, Any

from config import MEMORY_V2_ENABLED, MEMORY_V2_READ_ENABLED, MEMORY_MAX_INJECTION_TOKENS
from database import SessionLocal
from layer_a import memory_store
from layer_a import memory_index
from layer_a.memory_router import route_query
from layer_a.memory_scoring import rerank_results
from layer_a.memory_compact import compact_retrieved_context

logger = logging.getLogger(__name__)

def retrieve_context(user_id: str, query: str, max_tokens: int = MEMORY_MAX_INJECTION_TOKENS) -> Dict[str, Any]:
    """
    現在の質問に必要な個人コンテキストを小さく返す。
    戻り値:
    {
      "core_view": "...",
      "active_view": "...",
      "context_capsule": "...",
      "used_memory_ids": ["..."],
      "token_estimate": 512
    }
    """
    if not MEMORY_V2_ENABLED or not MEMORY_V2_READ_ENABLED:
        return {
            "core_view": "",
            "active_view": "",
            "context_capsule": "",
            "used_memory_ids": [],
            "token_estimate": 0
        }

    db = SessionLocal()
    try:
        # 1. Route Query
        route_info = route_query(query)
        needs_profile = route_info.get("needs_profile", True)
        needs_active_state = route_info.get("needs_active_state", True)
        memory_types = route_info.get("memory_types", ["preference", "principle", "state"])

        core_view = ""
        active_view = ""
        token_estimate = 0
        
        # 2. Base Views取得
        if needs_profile:
            view_item = memory_store.get_memory_view(db, user_id, "core_200")
            if view_item:
                core_view = view_item.content_text
                token_estimate += view_item.token_estimate

        if needs_active_state:
            view_item = memory_store.get_memory_view(db, user_id, "active_300")
            if view_item:
                active_view = view_item.content_text
                token_estimate += view_item.token_estimate

        # 3. Candidate Retrieval (Chroma)
        raw_results = memory_index.search_memory_items(
            query=query,
            user_id=user_id,
            status="active",
            memory_types=None, # In a more complex filter, we might pass memory_types
            limit=20
        )
        
        items_for_rerank = []
        if raw_results and raw_results.get("documents") and len(raw_results["documents"]) > 0:
            for d, m, dist in zip(raw_results["documents"][0], raw_results["metadatas"][0], raw_results["distances"][0]):
                # Filter by memory types from router if needed, though Chroma query might lack direct type IN () filtering.
                if memory_types and m.get("memory_type") not in memory_types:
                    continue
                items_for_rerank.append({
                    "id": m.get("memory_id"),
                    "document": d,
                    "metadata": m
                })
            
            # Semantic distances are passed out implicitly in our reranker logic
            # but here they are tightly coupled with the loop above.
            distances = raw_results["distances"][0]
        else:
            distances = []

        # 4. Rerank
        diverse_results = rerank_results(items_for_rerank, distances, max_items=5)

        # 5. Compact context
        # Check remaining budget
        remaining_budget = max_tokens - token_estimate
        if remaining_budget > 0 and diverse_results:
            compact_res = compact_retrieved_context(query, diverse_results)
            context_capsule = compact_res.get("context_capsule", "")
            used_ids = compact_res.get("cited_memory_ids", [])
            # Assume 1 token ~ 4 chars for english or 1 char for CJK, simplistic approximation
            token_estimate += len(context_capsule) // 2 
        else:
            context_capsule = ""
            used_ids = []

        return {
            "core_view": core_view,
            "active_view": active_view,
            "context_capsule": context_capsule,
            "used_memory_ids": used_ids,
            "token_estimate": token_estimate
        }

    except Exception as e:
        logger.error(f"Error in retrieve_context: {e}")
        return {
            "core_view": "",
            "active_view": "",
            "context_capsule": "",
            "used_memory_ids": [],
            "token_estimate": 0
        }
    finally:
        db.close()
