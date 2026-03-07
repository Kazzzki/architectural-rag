import pytest
from unittest.mock import patch, MagicMock

from layer_a.memory_retrieve import retrieve_context

@patch('layer_a.memory_retrieve.SessionLocal')
@patch('layer_a.memory_store.get_memory_view')
@patch('layer_a.memory_index.search_memory_items')
@patch('layer_a.memory_retrieve.compact_retrieved_context')
@patch('layer_a.memory_retrieve.route_query')
def test_retrieve_context_budget(mock_route, mock_compact, mock_search, mock_views, mock_session):
    """クエリに応じて適切なtoken_budget内に収まったcontext_capsuleが返るかテスト"""
    mock_db = MagicMock()
    mock_session.return_value = mock_db
    
    mock_route.return_value = {
        "needs_profile": True,
        "needs_active_state": False,
        "memory_types": ["preference"]
    }
    
    # Views mock
    view_mock = MagicMock()
    view_mock.content_text = "Core text"
    view_mock.token_estimate = 50
    mock_views.return_value = view_mock
    
    # Search mock
    mock_search.return_value = {
        "documents": [["doc1", "doc2"]],
        "metadatas": [[
            {"memory_id": "m1", "memory_type": "preference"},
            {"memory_id": "m2", "memory_type": "preference"}
        ]],
        "distances": [[0.1, 0.2]]
    }
    
    # Compact mock
    mock_compact.return_value = {
        "context_capsule": "Short summarized facts",
        "cited_memory_ids": ["m1", "m2"]
    }
    
    res = retrieve_context("u1", "私の好みは？", max_tokens=900)
    
    assert "Core text" in res["core_view"]
    assert "Short summarized facts" in res["context_capsule"]
    assert "m1" in res["used_memory_ids"]
    assert res["token_estimate"] >= 50
    assert res["token_estimate"] <= 900
