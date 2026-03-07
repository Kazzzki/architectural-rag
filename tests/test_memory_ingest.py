import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from database import SessionLocal, MemoryItem
from layer_a import memory_store
from layer_a.memory_ingest import ingest_conversation
from layer_a.memory_models import MemoryCandidate

@pytest.fixture
def mock_db():
    # In-memory session mock or actual SQLite test DB
    pass

@patch('layer_a.memory_ingest.extract_candidates')
@patch('layer_a.memory_ingest.decide_merge_action')
@patch('layer_a.memory_index.upsert_memory_item')
@patch('layer_a.memory_ingest.SessionLocal')
def test_ingest_conversation_adds_preference(mock_session_constructor, mock_upsert, mock_merge, mock_extract):
    """preferenceが変わった際に旧アイテムがsupersededになり、新アイテムがactiveで追加されるかをテスト"""
    mock_db = MagicMock()
    mock_session_constructor.return_value = mock_db
    
    # 既存のアイテムをモック化
    old_item = MemoryItem(
        id="mem_old", user_id="u1", memory_type="preference", status="active",
        key_norm="food", canonical_text="好きな食べ物はリンゴ", support_count=1
    )
    
    # query().filter().first() のチェーンをモック
    query_mock = mock_db.query.return_value
    filter_mock = query_mock.filter.return_value
    filter_mock.first.return_value = old_item

    mock_extract.return_value = [
        MemoryCandidate(
            memory_type="preference",
            key_norm="food",
            canonical_text="好きな食べ物はバナナ",
            confidence=0.9
        )
    ]
    
    mock_merge.return_value = {
        "action": "SUPERSEDE",
        "target_memory_id": "mem_old",
        "new_memory": {"canonical_text": "好きな食べ物はバナナ"}
    }
    
    messages = [{"role": "user", "content": "実はバナナも好きだよ"}]
    res = ingest_conversation("u1", "conv_1", messages)
    
    assert res["status"] == "completed"
    assert res["saved"] == 1
    # Check if existing item was superseded
    assert old_item.status == "superseded"
    
@patch('layer_a.memory_ingest.extract_candidates')
def test_ingest_conversation_skips_junk(mock_extract):
    """ありがとう等のJunkが保存されないことをテスト"""
    # Junkはextract_candidates内部で弾かれるよう実装されている前提
    mock_extract.return_value = []
    
    messages = [{"role": "user", "content": "ありがとう！"}]
    res = ingest_conversation("u1", "conv_2", messages)
    
    assert res["status"] == "completed"
    assert res["saved"] == 0
