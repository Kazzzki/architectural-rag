# backend/conversation_scope.py
# Phase 6: 会話スコープの定義

from pydantic import BaseModel, Field
from typing import Optional

class ConversationScope(BaseModel):
    """
    1回のチャットリクエストにおける「前提（スコープ）」を定義する。
    - project_id: 対象プロジェクト
    - lens: 視点（例: "manager", "engineer"）
    - task_mode: タスクモード（例: "explore", "draft"）
    - scope_version: アプリやデータ構造のバージョンを示すハッシュ/タグ
    """
    project_id: Optional[str] = None
    lens: str = "general"
    task_mode: str = "explore"
    scope_version: str = "v1"

def create_scope(project_id: Optional[str] = None, lens: str = "general", task_mode: str = "explore", scope_version: str = "v1") -> ConversationScope:
    return ConversationScope(
        project_id=project_id,
        lens=lens,
        task_mode=task_mode,
        scope_version=scope_version
    )
