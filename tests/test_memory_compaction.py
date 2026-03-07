import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from database import MemoryItem
from layer_a.memory_compaction_job import run_compaction

@patch('layer_a.memory_compaction_job.SessionLocal')
@patch('layer_a.memory_store.get_active_memories')
@patch('layer_a.memory_store.add_memory_history')
def test_run_compaction_demotes_stale_state(mock_history, mock_get_active, mock_session):
    """古いstateがactiveからarchivedに降格するかのテスト"""
    mock_db = MagicMock()
    mock_session.return_value = mock_db
    
    now = datetime(2026, 3, 7, 12, 0, 0)
    stale_date = now - timedelta(days=35) # 30日以上前
    
    stale_state = MemoryItem(
        id="s1", user_id="u1", memory_type="state", status="active",
        created_at=stale_date, last_used_at=stale_date
    )
    
    fresh_state = MemoryItem(
        id="s2", user_id="u1", memory_type="state", status="active",
        created_at=stale_date, last_used_at=now - timedelta(days=2) # 最近使われた
    )
    
    mock_get_active.return_value = [stale_state, fresh_state]
    
    res = run_compaction("u1", now.isoformat())
    
    assert res["status"] == "success"
    assert res["states_demoted"] == 1
    assert stale_state.status == "archived"
    assert fresh_state.status == "active"
