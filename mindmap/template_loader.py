"""
テンプレートローダー（v2統一フォーマット対応）
defaults/ + templates/ からYAMLテンプレートを読み込み、
バリデーション・マージ・キャッシュを行う。
"""
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple

logger = logging.getLogger(__name__)

# ディレクトリ定義
DATA_DIR = Path(__file__).parent / "data"
DEFAULTS_DIR = DATA_DIR / "defaults"
TEMPLATES_DIR = DATA_DIR / "templates"

# キャッシュ
_cache: Dict[str, Dict[str, Any]] = {}


class TemplateValidationError(Exception):
    """テンプレートバリデーションエラー"""
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"Validation failed with {len(errors)} error(s)")


def load_template(template_id: str) -> Dict[str, Any]:
    """
    テンプレートを読み込む。
    1. defaults/ から組み込みテンプレートを探す
    2. templates/ からユーザーテンプレートを探す（上書き優先）
    3. バリデーションを実行
    4. キャッシュに格納
    """
    if template_id in _cache:
        return _cache[template_id]
    
    # defaults/ から探す
    default_path = DEFAULTS_DIR / f"{template_id}.yaml"
    template_path = TEMPLATES_DIR / f"{template_id}.yaml"
    
    data = None
    
    if default_path.exists():
        data = _load_yaml(default_path)
    
    if template_path.exists():
        user_data = _load_yaml(template_path)
        if data:
            # ユーザーテンプレートがdefaultsを上書き
            data = _merge_templates(data, user_data)
        else:
            data = user_data
    
    if data is None:
        raise FileNotFoundError(f"Template '{template_id}' not found in defaults/ or templates/")
    
    # 後方互換: metaが無い場合は旧形式として処理
    data = _ensure_v2_format(data)
    
    _cache[template_id] = data
    return data


def list_templates() -> List[Dict[str, Any]]:
    """利用可能なテンプレート一覧"""
    templates = {}
    
    # defaults/ をスキャン
    if DEFAULTS_DIR.exists():
        for f in DEFAULTS_DIR.glob("*.yaml"):
            tid = f.stem
            data = _load_yaml(f)
            if data:
                data = _ensure_v2_format(data)
                meta = data.get("meta", {})
                templates[tid] = {
                    "id": tid,
                    "name": meta.get("name", tid),
                    "description": meta.get("description", ""),
                    "icon": meta.get("icon", "📋"),
                    "tags": meta.get("tags", []),
                    "version": meta.get("version", "1.0"),
                    "source": "default",
                    "node_count": len(data.get("nodes", [])),
                    "edge_count": len(data.get("edges", [])),
                }
    
    # templates/ をスキャン（上書き）
    if TEMPLATES_DIR.exists():
        for f in TEMPLATES_DIR.glob("*.yaml"):
            tid = f.stem
            data = _load_yaml(f)
            if data:
                data = _ensure_v2_format(data)
                meta = data.get("meta", {})
                templates[tid] = {
                    "id": tid,
                    "name": meta.get("name", tid),
                    "description": meta.get("description", ""),
                    "icon": meta.get("icon", "📋"),
                    "tags": meta.get("tags", []),
                    "version": meta.get("version", "1.0"),
                    "source": "user" if tid not in templates else "override",
                    "node_count": len(data.get("nodes", [])),
                    "edge_count": len(data.get("edges", [])),
                }
    
    return list(templates.values())


def validate_template(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    テンプレートを検証する。
    Returns: (is_valid, error_messages)
    """
    errors = []
    
    # 必須セクション
    if "nodes" not in data or not data["nodes"]:
        errors.append("'nodes' セクションが必要です")
    if "edges" not in data or not data["edges"]:
        errors.append("'edges' セクションが必要です")
    
    # ノードID重複チェック
    node_ids: Set[str] = set()
    for node in data.get("nodes", []):
        if "id" not in node:
            errors.append(f"ノードにIDがありません: {node.get('label', '不明')}")
            continue
        if node["id"] in node_ids:
            errors.append(f"ノードIDが重複しています: {node['id']}")
        node_ids.add(node["id"])
    
    # エッジID重複・参照整合性チェック
    edge_ids: Set[str] = set()
    for edge in data.get("edges", []):
        if "id" not in edge:
            errors.append(f"エッジにIDがありません")
            continue
        if edge["id"] in edge_ids:
            errors.append(f"エッジIDが重複しています: {edge['id']}")
        edge_ids.add(edge["id"])
        
        if edge.get("source") not in node_ids:
            errors.append(f"エッジ {edge['id']} のsource '{edge.get('source')}' が見つかりません")
        if edge.get("target") not in node_ids:
            errors.append(f"エッジ {edge['id']} のtarget '{edge.get('target')}' が見つかりません")
    
    # フェーズ / カテゴリの参照整合性（ID or 名前どちらでも許可）
    if "phases" in data:
        phase_ids = {p["id"] for p in data["phases"] if "id" in p}
        phase_names = {p["name"] for p in data["phases"] if "name" in p}
        phase_valid = phase_ids | phase_names
        for node in data.get("nodes", []):
            if node.get("phase") and node["phase"] not in phase_valid:
                errors.append(f"ノード {node['id']} のphase '{node['phase']}' がphases定義に見つかりません")
    
    if "categories" in data:
        category_ids = {c["id"] for c in data["categories"] if "id" in c}
        category_names = {c["name"] for c in data["categories"] if "name" in c}
        category_valid = category_ids | category_names
        for node in data.get("nodes", []):
            if node.get("category") and node["category"] not in category_valid:
                errors.append(f"ノード {node['id']} のcategory '{node['category']}' がcategories定義に見つかりません")
    
    # 循環依存検出
    cycle_errors = _detect_cycles(data.get("nodes", []), data.get("edges", []))
    errors.extend(cycle_errors)
    
    # 知識データの参照整合性
    for k in data.get("knowledge", []):
        if k.get("node_id") not in node_ids:
            errors.append(f"知識データのnode_id '{k.get('node_id')}' がノードに見つかりません")
    
    return (len(errors) == 0, errors)


def get_knowledge_for_node(template_id: str, node_id: str) -> Optional[Dict[str, Any]]:
    """テンプレート内の知識データをノードIDで取得"""
    try:
        data = load_template(template_id)
        for k in data.get("knowledge", []):
            if k.get("node_id") == node_id:
                return k
        return None
    except Exception:
        return None


def clear_cache():
    """キャッシュをクリア"""
    _cache.clear()


# ── 内部関数 ──

def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """YAMLファイルを読み込み"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"YAML読み込みエラー ({path}): {e}")
        return None


def _ensure_v2_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    旧形式（v1）をv2形式に変換する。
    v1: id, name, description, nodes, edges
    v2: meta, phases, categories, nodes, edges, knowledge
    """
    if "meta" in data:
        return data  # 既にv2形式
    
    # v1 → v2 変換
    result = dict(data)
    
    # meta生成
    result["meta"] = {
        "id": data.get("id", "unknown"),
        "name": data.get("name", "不明なテンプレート"),
        "description": data.get("description", ""),
        "version": "1.0",
        "icon": "📋",
        "tags": [],
    }
    
    # トップレベルの id/name/description を除去
    for key in ["id", "name", "description"]:
        if key in result and "meta" in result:
            pass  # 残しておく（後方互換）
    
    # phases/categories を自動生成（ノードから抽出）
    if "phases" not in result:
        phases_seen = {}
        phase_map = {
            "基本計画": ("basic_plan", "#4A9EFF"),
            "基本設計": ("basic_design", "#22C55E"),
            "実施設計": ("detail_design", "#F59E0B"),
            "施工準備": ("construction_prep", "#EF4444"),
            "施工": ("construction", "#8B5CF6"),
        }
        order = 1
        for node in data.get("nodes", []):
            phase = node.get("phase", "")
            if phase and phase not in phases_seen:
                pid, color = phase_map.get(phase, (phase.lower().replace(" ", "_"), "#6B7280"))
                phases_seen[phase] = {"id": pid, "name": phase, "order": order, "color": color}
                order += 1
        result["phases"] = list(phases_seen.values())
    
    if "categories" not in result:
        categories_seen = {}
        category_map = {
            "管理": ("management", "#6B7280"),
            "構造": ("structure", "#EF4444"),
            "土木": ("civil", "#92400E"),
            "意匠": ("architecture", "#3B82F6"),
            "外装": ("exterior", "#10B981"),
            "設備": ("mep", "#8B5CF6"),
        }
        for node in data.get("nodes", []):
            cat = node.get("category", "")
            if cat and cat not in categories_seen:
                cid, color = category_map.get(cat, (cat.lower().replace(" ", "_"), "#6B7280"))
                categories_seen[cat] = {"id": cid, "name": cat, "color": color}
        result["categories"] = list(categories_seen.values())
    
    if "knowledge" not in result:
        result["knowledge"] = []
    
    return result


def _merge_templates(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """ベーステンプレートにオーバーライドをマージ"""
    result = dict(base)
    
    # メタ上書き
    if "meta" in override:
        result["meta"] = {**base.get("meta", {}), **override["meta"]}
    
    # phases/categories は完全置換
    for key in ["phases", "categories"]:
        if key in override:
            result[key] = override[key]
    
    # ノード: IDベースでマージ
    if "nodes" in override:
        base_nodes = {n["id"]: n for n in base.get("nodes", [])}
        for node in override["nodes"]:
            base_nodes[node["id"]] = {**base_nodes.get(node["id"], {}), **node}
        result["nodes"] = list(base_nodes.values())
    
    # エッジ: IDベースでマージ
    if "edges" in override:
        base_edges = {e["id"]: e for e in base.get("edges", [])}
        for edge in override["edges"]:
            base_edges[edge["id"]] = {**base_edges.get(edge["id"], {}), **edge}
        result["edges"] = list(base_edges.values())
    
    # 知識: node_idベースでマージ
    if "knowledge" in override:
        base_knowledge = {k["node_id"]: k for k in base.get("knowledge", [])}
        for k in override["knowledge"]:
            base_knowledge[k["node_id"]] = k
        result["knowledge"] = list(base_knowledge.values())
    
    return result


def _detect_cycles(nodes: List[Dict], edges: List[Dict]) -> List[str]:
    """有向グラフの循環を検出"""
    errors = []
    node_ids = {n["id"] for n in nodes if "id" in n}
    
    # 隣接リスト作成
    adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adj and tgt in node_ids:
            adj[src].append(tgt)
    
    # DFSで循環検出
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}
    
    def dfs(u: str, path: List[str]) -> bool:
        color[u] = GRAY
        path.append(u)
        for v in adj[u]:
            if color[v] == GRAY:
                cycle_start = path.index(v)
                cycle = path[cycle_start:] + [v]
                errors.append(f"循環依存を検出: {' → '.join(cycle)}")
                return True
            if color[v] == WHITE:
                if dfs(v, path):
                    return True
        color[u] = BLACK
        path.pop()
        return False
    
    for nid in node_ids:
        if color[nid] == WHITE:
            dfs(nid, [])
    
    return errors
