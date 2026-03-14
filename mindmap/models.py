"""
マインドマップ機能のデータモデル定義（v2統一フォーマット対応）
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

# --- Phase 1: Shared Constants ---
SOURCE_TYPES = ['manual', 'template', 'chat', 'gap_advisor', 'ai_expand']
FOCUS_AREAS = ['全体', '法規', '技術', '管理']
PHASE_OPTIONS = ["基本計画", "基本設計", "実施設計", "施工準備", "施工", "運用", "未設定"]
CATEGORY_OPTIONS = ["構造", "意匠", "設備", "外装", "土木", "管理", "法規", "その他"]


# v1後方互換用 Enum（主にproject_storeで継続使用）
class Phase(str, Enum):
    BASIC_PLANNING = "基本計画"
    BASIC_DESIGN = "基本設計"
    DETAIL_DESIGN = "実施設計"
    CONSTRUCTION_PREP = "施工準備"
    CONSTRUCTION = "施工"


class Category(str, Enum):
    STRUCTURE = "構造"
    ARCHITECTURE = "意匠"
    MEP = "設備"
    EXTERIOR = "外装"
    CIVIL = "土木"
    MANAGEMENT = "管理"


class EdgeType(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    INFO = "info"


class NodeStatus(str, Enum):
    NOT_STARTED = "未着手"
    IN_PROGRESS = "検討中"
    COMPLETED = "決定済み"


class Position(BaseModel):
    x: float
    y: float


# --- v2 テンプレートメタデータ ---

class TemplateMeta(BaseModel):
    id: str
    name: str
    description: str = ""
    version: str = "1.0"
    icon: str = "📋"
    tags: List[str] = []


class PhaseDefinition(BaseModel):
    id: str
    name: str
    order: int = 0
    color: str = "#6B7280"


class CategoryDefinition(BaseModel):
    id: str
    name: str
    color: str = "#6B7280"


class ProcessNode(BaseModel):
    id: str
    label: str
    description: str = ""
    phase: str  # v2: ID参照 (e.g. "basic_plan"), v1: 日本語 (e.g. "基本計画")
    category: str  # v2: ID参照 (e.g. "structure"), v1: 日本語 (e.g. "構造")
    checklist: List[str] = []
    deliverables: List[str] = []
    key_stakeholders: List[str] = []
    position: Position = Position(x=0, y=0)
    is_custom: bool = False
    status: NodeStatus = NodeStatus.NOT_STARTED
    ragResults: Optional[List[Dict[str, Any]]] = []
    chatHistory: Optional[List[Dict[str, Any]]] = []
    
    # Phase 1 additions
    source_type: str = "manual"
    checklist_total: int = 0
    checklist_done: int = 0
    deliverables_count: int = 0


class Edge(BaseModel):
    id: str = ""
    source: str
    target: str
    type: EdgeType = EdgeType.HARD
    reason: str = ""


class MindmapTemplate(BaseModel):
    """v2統一テンプレート"""
    meta: Optional[TemplateMeta] = None
    phases: List[PhaseDefinition] = []
    categories: List[CategoryDefinition] = []
    nodes: List[ProcessNode]
    edges: List[Edge]
    knowledge: List[Any] = []
    # v1後方互換
    id: str = ""
    name: str = ""
    description: str = ""


class TemplateListItem(BaseModel):
    id: str
    name: str
    description: str = ""
    icon: str = "📋"
    tags: List[str] = []
    version: str = "1.0"
    source: str = "default"  # "default" | "user" | "override"
    node_count: int = 0
    edge_count: int = 0


class ReverseTreeResponse(BaseModel):
    """逆引きツリーのレスポンス"""
    goal_node_id: str
    nodes: List[ProcessNode]
    edges: List[Edge]
    path_order: List[str]  # トポロジカル順のノードID


# --- Phase 2: Project Models ---

class CreateProjectRequest(BaseModel):
    name: str
    template_id: str


class ProjectListItem(BaseModel):
    id: str
    name: str
    description: str
    template_id: str
    created_at: str
    updated_at: str
    node_count: int = 0
    delta_count: int = 0
    
    # Phase 1 additions
    technical_conditions: str = ""
    legal_requirements: str = ""
    layer_b_project_id: str = ""
    gap_check_history: list = []


class ProjectData(BaseModel):
    id: str
    name: str
    description: str
    template_id: str
    created_at: str
    updated_at: str
    delta_count: int = 0
    
    # Phase 1 additions
    technical_conditions: str = ""
    legal_requirements: str = ""
    layer_b_project_id: str = ""
    gap_check_history: list = []
    
    nodes: List[ProcessNode]
    edges: List[Edge]


class NodeUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    phase: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    checklist: Optional[List[str]] = None
    deliverables: Optional[List[str]] = None
    key_stakeholders: Optional[List[str]] = None
    notes: Optional[str] = None
    ragResults: Optional[List[Dict[str, Any]]] = None
    chatHistory: Optional[List[Dict[str, Any]]] = None
    source_type: Optional[str] = None


class NodeCreate(BaseModel):
    label: str = "新規ノード"
    description: str = ""
    phase: str = "基本計画"
    category: str = "管理"
    pos_x: float = 400
    pos_y: float = 400
    checklist: List[str] = []
    deliverables: List[str] = []
    key_stakeholders: List[str] = []
    source_type: str = "manual"


class EdgeCreate(BaseModel):
    source: str
    target: str
    type: str = "hard"
    reason: str = ""


class EdgeUpdate(BaseModel):
    source: Optional[str] = None
    target: Optional[str] = None
    type: Optional[str] = None
    reason: Optional[str] = None


# --- Phase 3: Knowledge Models ---

class KnowledgeDepth(str, Enum):
    OVERVIEW = "overview"      # 概要レベル
    PRACTICAL = "practical"    # 実践レベル
    EXPERT = "expert"          # 専門レベル


class KnowledgeEntry(BaseModel):
    depth: KnowledgeDepth
    title: str
    content: str
    references: List[str] = []


class KnowledgeNode(BaseModel):
    """ノードに紐づく知識データ"""
    node_id: str
    entries: List[KnowledgeEntry] = []


class ProjectImportRequest(BaseModel):
    name: str
    nodes: List[ProcessNode]
    edges: List[Edge]
    template_id: str = "blank"

class AIActionRequest(BaseModel):
    action: str
    nodeId: str
    content: str
    context: Optional[Dict[str, Any]] = None


# --- Phase 1: Gap Advisor Models ---
class ProjectContextUpdate(BaseModel):
    technical_conditions: Optional[str] = None
    legal_requirements: Optional[str] = None


class GapCheckRequest(BaseModel):
    project_context_override: Optional[str] = None
    focus_areas: Optional[List[str]] = None
    focus_area: Optional[str] = None # Task-1 Compatibility


class GapApplyRequest(BaseModel):
    suggestions: List[Dict[str, Any]]


# --- AI Link Prediction / Mentions ---
class UnlinkedMentionsRequest(BaseModel):
    node_id: str

class PredictLinksRequest(BaseModel):
    new_node_id: str


class NodeFromTextRequest(BaseModel):
    text: str
    source_type: str = "manual"
