from datetime import datetime
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, Field

MemoryType = Literal['preference', 'principle', 'state', 'episode', 'summary']
MemoryStatus = Literal['active', 'superseded', 'archived', 'tombstoned']
MemoryAction = Literal['add', 'merge', 'update', 'supersede', 'archive', 'tombstone', 'restore']
MemoryGranularity = Literal['daily', 'weekly', 'monthly', 'yearly']
ViewName = Literal['core_200', 'active_300', 'profile_800', 'yearly_digest']
SalienceFlag = Literal['decision', 'failure', 'exception', 'milestone', 'first', 'last', 'none']

class MemoryCandidate(BaseModel):
    """LLMから抽出されたばかりのメモリ候補"""
    memory_type: MemoryType
    key_norm: Optional[str] = None
    title: Optional[str] = None
    canonical_text: str
    value_json: Optional[dict] = None
    tags: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    evidence_quote: Optional[str] = None
    confidence: float = 0.0
    personalness: float = 0.0
    reusability: float = 0.0
    longevity: float = 0.0
    distinctiveness: float = 0.0
    salience_flags: List[SalienceFlag] = Field(default_factory=lambda: ["none"])
    ttl_days: Optional[int] = None
    reason: Optional[str] = None

class MemoryItemModel(BaseModel):
    """DBレイヤのメモリエンティティ表現"""
    id: str
    user_id: str
    memory_type: MemoryType
    status: MemoryStatus
    key_norm: Optional[str] = None
    title: Optional[str] = None
    canonical_text: str
    value_json: Optional[dict] = None
    tags_json: Optional[list] = None
    entities_json: Optional[list] = None
    confidence: float = 0.0
    salience: float = 0.0
    utility_score: float = 0.0
    support_count: int = 1
    contradiction_count: int = 0
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_confirmed_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    supersedes_id: Optional[str] = None
    source_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class ContextCapsule(BaseModel):
    """検索後のコンパクト化されたコンテキスト表現"""
    context_capsule: str
    cited_memory_ids: List[str]
    uncertainty_notes: Optional[str] = None

class ContextRetrievalResult(BaseModel):
    """Retrievalパイプラインからの最終戻り値"""
    core_view: Optional[str] = None
    active_view: Optional[str] = None
    context_capsule: str
    used_memory_ids: List[str]
    token_estimate: int
