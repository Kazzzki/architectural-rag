"""
マインドマップ API ルーター（v2対応）
"""
import os
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, File, UploadFile

from .models import (
    ProcessNode, Edge, MindmapTemplate, TemplateMeta,
    PhaseDefinition, CategoryDefinition,
    TemplateListItem, ReverseTreeResponse, Position,
    CreateProjectRequest, ProjectListItem, ProjectData,
    NodeUpdate, NodeCreate, EdgeCreate,
    KnowledgeNode, KnowledgeEntry, KnowledgeDepth,
    ProjectImportRequest, AIActionRequest
)
from pydantic import BaseModel
from .graph_service import GraphService
from . import project_store
from . import template_loader
from . import api_settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mindmap", tags=["mindmap"])

# 知識キャッシュ（template_loader + 旧knowledge/のフォールバック）
_knowledge_cache: Dict[str, KnowledgeNode] = {}
KNOWLEDGE_DIR = Path(__file__).parent / "data" / "knowledge"


def _load_template(template_id: str) -> MindmapTemplate:
    """template_loaderを使ってYAMLを読み込み、MindmapTemplateに変換する"""
    try:
        data = template_loader.load_template(template_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")
    except Exception as e:
        logger.error(f"Template load error: {e}")
        raise HTTPException(status_code=500, detail=f"Template load error: {str(e)}")

    meta = data.get("meta", {})

    # ノードを変換
    nodes = []
    for n in data.get('nodes', []):
        pos = n.get('position', {}) if isinstance(n.get('position'), dict) else {}
        node = ProcessNode(
            id=n['id'],
            label=n['label'],
            description=n.get('description', ''),
            phase=n.get('phase', ''),
            category=n.get('category', ''),
            checklist=n.get('checklist', []),
            deliverables=n.get('deliverables', []),
            key_stakeholders=n.get('key_stakeholders', []),
            position=Position(x=pos.get('x', 0), y=pos.get('y', 0)),
            is_custom=n.get('is_custom', False),
        )
        nodes.append(node)

    # エッジを変換
    edges = []
    for e in data.get('edges', []):
        edge = Edge(
            id=e.get('id', f"{e['source']}_{e['target']}"),
            source=e['source'],
            target=e['target'],
            type=e.get('type', 'hard'),
            reason=e.get('reason', ''),
        )
        edges.append(edge)

    # phases / categories 変換
    phases = [
        PhaseDefinition(**p) for p in data.get('phases', [])
    ]
    categories = [
        CategoryDefinition(**c) for c in data.get('categories', [])
    ]

    template = MindmapTemplate(
        id=meta.get('id', template_id),
        name=meta.get('name', template_id),
        description=meta.get('description', ''),
        meta=TemplateMeta(**meta) if meta else None,
        phases=phases,
        categories=categories,
        nodes=nodes,
        edges=edges,
        knowledge=data.get('knowledge', []),
    )
    return template


def _list_templates() -> List[TemplateListItem]:
    """利用可能なテンプレート一覧を取得"""
    items = template_loader.list_templates()
    return [TemplateListItem(**item) for item in items]


def _load_knowledge(node_id: str) -> Optional[KnowledgeNode]:
    """ノードIDに対応する知識データを読み込む（統一YAML + 旧knowledge/フォールバック）"""
    if node_id in _knowledge_cache:
        return _knowledge_cache[node_id]

    # 1. 統一テンプレートの knowledge セクションから検索
    for tmpl_info in template_loader.list_templates():
        try:
            data = template_loader.load_template(tmpl_info["id"])
            for item in data.get('knowledge', []):
                nid = item.get('node_id', '')
                entries = [
                    KnowledgeEntry(
                        depth=e.get('depth', 'overview'),
                        title=e.get('title', ''),
                        content=e.get('content', ''),
                        references=e.get('references', []),
                    )
                    for e in item.get('entries', [])
                ]
                _knowledge_cache[nid] = KnowledgeNode(node_id=nid, entries=entries)
        except Exception as e:
            logger.debug(f"Knowledge load from template: {e}")

    if node_id in _knowledge_cache:
        return _knowledge_cache[node_id]

    # 2. 旧 knowledge/ ディレクトリのフォールバック
    if KNOWLEDGE_DIR.exists():
        for yaml_file in KNOWLEDGE_DIR.glob("*.yaml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                if not data:
                    continue
                for item in data.get('knowledge', []):
                    nid = item.get('node_id', '')
                    entries = [
                        KnowledgeEntry(
                            depth=e.get('depth', 'overview'),
                            title=e.get('title', ''),
                            content=e.get('content', ''),
                            references=e.get('references', []),
                        )
                        for e in item.get('entries', [])
                    ]
                    _knowledge_cache[nid] = KnowledgeNode(node_id=nid, entries=entries)
            except Exception as e:
                logger.warning(f"Knowledge load error {yaml_file}: {e}")

    return _knowledge_cache.get(node_id)


# ── Template API Endpoints ──

@router.get("/templates", response_model=List[TemplateListItem])
async def get_templates():
    """テンプレート一覧を取得"""
    return _list_templates()


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """テンプレートの全データ（ノード＋エッジ＋phases/categories）を取得"""
    return _load_template(template_id)


@router.get("/templates/{template_id}/validate")
async def validate_template(template_id: str):
    """テンプレートを検証"""
    try:
        data = template_loader.load_template(template_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Template not found")
    is_valid, errors = template_loader.validate_template(data)
    return {"valid": is_valid, "errors": errors}


@router.get("/tree/{template_id}/{node_id}", response_model=ReverseTreeResponse)
async def get_reverse_tree(template_id: str, node_id: str):
    """ゴールノードから逆引き依存ツリーを取得"""
    template = _load_template(template_id)
    gs = GraphService(template)
    try:
        return gs.get_reverse_tree(node_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/path/{template_id}/{from_id}/{to_id}")
async def get_critical_path(template_id: str, from_id: str, to_id: str):
    """2点間のクリティカルパスを取得"""
    template = _load_template(template_id)
    gs = GraphService(template)
    try:
        path = gs.get_critical_path(from_id, to_id)
        return {"path": path}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Project CRUD Endpoints (v2 delta) ──

@router.get("/projects")
async def list_projects():
    """プロジェクト一覧（進捗情報付き）"""
    projects = project_store.list_projects()
    result = []
    for p in projects:
        item = {
            "id": p["id"],
            "name": p["name"],
            "description": p.get("description", ""),
            "template_id": p["template_id"],
            "building_type": p.get("building_type", ""),
            "status": p.get("status", "active"),
            "created_at": p["created_at"],
            "updated_at": p["updated_at"],
            "node_count": p.get("node_count", 0),
            "delta_count": p.get("delta_count", 0),
        }
        # 進捗計算
        try:
            template = _load_template(p["template_id"])
            progress = project_store.get_progress(p["id"], template)
            item["progress"] = progress
        except Exception:
            item["progress"] = {"total": 0, "completed": 0, "in_progress": 0, "percent": 0}
        result.append(item)
    return result


@router.post("/projects")
async def create_project(req: CreateProjectRequest):
    """テンプレートからプロジェクトをフォーク（delta方式）"""
    template = _load_template(req.template_id)
    project_id = project_store.create_project(req.name, template)
    return {
        "id": project_id,
        "name": req.name,
        "template_id": req.template_id,
        "message": f"プロジェクト作成: {req.name}",
    }


@router.post("/projects/import")
async def import_project(req: ProjectImportRequest):
    """分析結果などを元にプロジェクトを作成（blankテンプレート + delta）"""
    try:
        # blankテンプレートをベースにプロジェクト作成
        template = _load_template(req.template_id)
        project_id = project_store.create_project(req.name, template)
        
        # ノードを追加
        for node in req.nodes:
            # プロジェクトのルートノードとIDが重複する場合（rootなど）はmodify扱いにする
            # ただし、blankテンプレートは "root" ノードを持つため、
            # インポートデータも "root" を持っていれば上書き更新したい。
            # project_store.add_node は常に新しいIDを生成するわけではなく、ID指定も可能（delta type=add_node）
            # ここではシンプルに、全てのノードを add_node として記録する。
            # blankテンプレートの初期ノードと衝突する場合は、後勝ちで delta が適用されるはず？
            # project_store.get_project_with_merged_data のロジックでは:
            # 1. テンプレートノード展開
            # 2. Delta適用 (add_node -> 上書き)
            # なので、add_node で同IDを送れば上書きになる。
            
            node_data = node.model_dump()
            # 座標データの構造調整
            if hasattr(node, "position"):
                node_data["pos_x"] = node.position.x
                node_data["pos_y"] = node.position.y
                del node_data["position"]

            # ステータス調整
            if "status" in node_data and isinstance(node_data["status"], Enum):
                node_data["status"] = node_data["status"].value

            project_store.add_node(project_id, node_data)

        # エッジを追加
        for edge in req.edges:
            edge_data = edge.model_dump()
            if "type" in edge_data and isinstance(edge_data["type"], Enum):
                edge_data["type"] = edge_data["type"].value
            project_store.add_edge(project_id, edge_data)
            
        return {
            "id": project_id,
            "name": req.name,
            "message": f"プロジェクトをインポートしました: {len(req.nodes)} nodes",
        }
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Project import failed: {str(e)}")


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """プロジェクトの全データを取得（テンプレート + delta マージ済み）"""
    raw = project_store.get_project_data(project_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Project not found")

    template = _load_template(raw["project"]["template_id"])
    merged = project_store.get_project_with_merged_data(project_id, template)
    if not merged:
        raise HTTPException(status_code=500, detail="Failed to merge project data")

    return ProjectData(
        id=merged['project']['id'],
        name=merged['project']['name'],
        description=merged['project'].get('description', ''),
        template_id=merged['project']['template_id'],
        created_at=merged['project']['created_at'],
        updated_at=merged['project']['updated_at'],
        nodes=merged['nodes'],
        edges=merged['edges'],
    )


@router.get("/projects/{project_id}/progress")
async def get_project_progress(project_id: str):
    """プロジェクト進捗"""
    raw = project_store.get_project_data(project_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Project not found")
    template = _load_template(raw["project"]["template_id"])
    return project_store.get_progress(project_id, template)


@router.get("/projects/{project_id}/next-actions")
async def get_next_actions(project_id: str):
    """依存解決済みの次のアクション一覧"""
    raw = project_store.get_project_data(project_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Project not found")
    template = _load_template(raw["project"]["template_id"])
    return project_store.get_next_actions(project_id, template)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """プロジェクト削除"""
    if not project_store.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "削除完了"}


# Node operations
@router.put("/projects/{project_id}/nodes/{node_id}")
async def update_node(project_id: str, node_id: str, update: NodeUpdate):
    """ノードを更新（差分記録）"""
    updates = update.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided")
    if not project_store.update_node(project_id, node_id, updates):
        raise HTTPException(status_code=404, detail="Node not found")
    return {"message": "更新完了"}


@router.post("/projects/{project_id}/nodes")
async def add_node(project_id: str, node: NodeCreate):
    """カスタムノードを追加（差分記録）"""
    node_data = node.model_dump()
    node_id = project_store.add_node(project_id, node_data)
    return {"id": node_id, "message": "ノード追加完了"}


@router.delete("/projects/{project_id}/nodes/{node_id}")
async def delete_node(project_id: str, node_id: str):
    """ノードと関連エッジを削除（差分記録）"""
    if not project_store.delete_node(project_id, node_id):
        raise HTTPException(status_code=404, detail="Node not found")
    return {"message": "削除完了"}


# Edge operations
@router.post("/projects/{project_id}/edges")
async def add_edge(project_id: str, edge: EdgeCreate):
    """エッジを追加（差分記録）"""
    edge_data = edge.model_dump()
    edge_id = project_store.add_edge(project_id, edge_data)
    return {"id": edge_id, "message": "エッジ追加完了"}


@router.delete("/projects/{project_id}/edges/{edge_id}")
async def delete_edge(project_id: str, edge_id: str):
    """エッジを削除（差分記録）"""
    if not project_store.delete_edge(project_id, edge_id):
        raise HTTPException(status_code=404, detail="Edge not found")
    return {"message": "削除完了"}


# Undo
@router.post("/projects/{project_id}/undo")
async def undo_action(project_id: str):
    """最後の操作を元に戻す"""
    result = project_store.undo(project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Undo不可（履歴なし）")
    return result


# ── Knowledge API Endpoints ──

@router.get("/knowledge/{node_id}")
async def get_knowledge(node_id: str):
    """ノードに紐づく知識データを取得"""
    knowledge = _load_knowledge(node_id)
    if not knowledge:
        return KnowledgeNode(node_id=node_id, entries=[])
    return knowledge


# ── API Settings Endpoints ──

@router.get("/settings")
async def get_settings():
    """API設定を取得（キーはマスク表示）"""
    settings = api_settings.load_settings()
    # APIキーをマスク
    key = settings.get("gemini_api_key", "")
    if key:
        settings["gemini_api_key_masked"] = key[:8] + "*" * (len(key) - 12) + key[-4:] if len(key) > 12 else "***"
        settings["has_api_key"] = True
    else:
        settings["gemini_api_key_masked"] = ""
        settings["has_api_key"] = False
    # 生のキーは返さない
    del settings["gemini_api_key"]
    return settings


@router.put("/settings")
async def update_settings(request: dict):
    """API設定を更新"""
    updated = api_settings.save_settings(request)
    # レスポンスもマスク
    key = updated.get("gemini_api_key", "")
    if key:
        updated["gemini_api_key_masked"] = key[:8] + "*" * (len(key) - 12) + key[-4:] if len(key) > 12 else "***"
        updated["has_api_key"] = True
    else:
        updated["gemini_api_key_masked"] = ""
        updated["has_api_key"] = False
    del updated["gemini_api_key"]
    return {"message": "設定を保存しました", "settings": updated}


@router.get("/fs/scan")
async def scan_filesystem(path: str, max_depth: int = 3):
    """ローカルファイルシステムをスキャンしてMindmap形式（ノード+エッジ）で返す"""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Path not found")
    
    root_path = Path(path).resolve()
    nodes = []
    edges = []
    
    # ノード追加ヘルパー
    def add_node_obj(p: Path, x: float, y: float, is_dir: bool):
        node_id = str(p)
        label = p.name if p != root_path else str(p)  # ルートはフルパス
        # シンプルな色分け
        color = "#fbbf24" if is_dir else "#ffffff" # amber-400 for dir, white for file
        
        nodes.append({
            "id": node_id,
            "type": "custom",
            "position": {"x": x, "y": y},
            "data": {
                "label": label,
                "color": color,
                "role": "structure", # スタイル用
                "is_dir": is_dir
            }
        })

    # 再帰的にスキャンしてツリー構造を構築
    # レイアウト計算用に、まずツリー構造をメモリ上に作る
    tree = {"path": root_path, "children": []}
    
    # ノード数制限
    MAX_NODES = 500
    node_count = 0
    
    def build_tree(current_node, current_depth):
        nonlocal node_count
        if current_depth >= max_depth:
            return
        
        try:
            # ディレクトリ以外はスキップ（子を持たない）
            if not current_node["path"].is_dir():
                return

            for entry in sorted(os.scandir(current_node["path"]), key=lambda e: (not e.is_dir(), e.name)):
                if node_count >= MAX_NODES:
                    break
                
                # 隠しファイル除外
                if entry.name.startswith('.'):
                    continue
                    
                child = {"path": Path(entry.path), "children": []}
                current_node["children"].append(child)
                node_count += 1
                
                if entry.is_dir():
                    build_tree(child, current_depth + 1)
                    
        except PermissionError:
            pass

    build_tree(tree, 0)

    # レイアウト計算 (Simple Tree Layout to the Right)
    X_GAP = 300
    Y_GAP = 80
    
    current_y = 0
    
    def layout_tree(node, depth):
        nonlocal current_y
        
        my_y = 0
        
        if not node["children"]:
            # Leaf node
            my_y = current_y
            current_y += Y_GAP
        else:
            # Parent node: Y is average of children
            child_ys = []
            for child in node["children"]:
                child_ys.append(layout_tree(child, depth + 1))
            my_y = sum(child_ys) / len(child_ys)
            
        # ノード生成
        add_node_obj(node["path"], x=depth * X_GAP, y=my_y, is_dir=node["path"].is_dir())
        
        # エッジ生成 (Parent -> Child)
        for child in node["children"]:
            edges.append({
                "id": f"{node['path']}__{child['path']}",
                "source": str(node["path"]),
                "target": str(child["path"]),
                "type": "hard"
            })
            
        return my_y

    layout_tree(tree, 0)
    
    return {
        "nodes": nodes,
        "edges": edges,
        "root_id": str(root_path)
    }


@router.post("/fs/analyze")
async def analyze_text_files(request: dict):
    """テキストファイルを読み込み、Gemini APIで分析してマインドマップ構造を生成する"""
    file_path = request.get("path", "")
    max_files = request.get("max_files", 20)
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Path not found")
    
    target_path = Path(file_path).resolve()
    
    # 対応拡張子
    TEXT_EXTENSIONS = {'.txt', '.md', '.csv', '.log', '.json', '.yaml', '.yml', '.xml', '.html', '.htm', '.py', '.js', '.ts', '.tsx', '.jsx', '.css', '.sql', '.sh', '.bat', '.ini', '.cfg', '.conf', '.env', '.rst', '.tex'}
    
    # ファイル収集
    file_contents = []
    
    if target_path.is_file():
        try:
            content = target_path.read_text(encoding='utf-8', errors='ignore')[:10000]
            file_contents.append({"name": target_path.name, "content": content})
        except Exception as e:
            logger.warning(f"File read error: {e}")
    elif target_path.is_dir():
        count = 0
        for entry in sorted(os.scandir(target_path), key=lambda e: e.name):
            if count >= max_files:
                break
            if entry.is_file() and not entry.name.startswith('.'):
                ext = Path(entry.name).suffix.lower()
                if ext in TEXT_EXTENSIONS:
                    try:
                        content = Path(entry.path).read_text(encoding='utf-8', errors='ignore')[:10000]
                        file_contents.append({"name": entry.name, "content": content})
                        count += 1
                    except Exception as e:
                        logger.warning(f"File read error {entry.name}: {e}")
    
    if not file_contents:
        raise HTTPException(status_code=400, detail="テキストファイルが見つかりません。対応拡張子: " + ", ".join(sorted(TEXT_EXTENSIONS)))
    
    return await _analyze_with_gemini(file_contents)


@router.post("/fs/upload-analyze")
async def upload_and_analyze(files: List[UploadFile] = File(...)):
    """アップロードされたファイルをGemini AIで分析してマインドマップを生成する"""
    
    TEXT_EXTENSIONS = {'.txt', '.md', '.csv', '.log', '.json', '.yaml', '.yml', '.xml', '.html', '.htm', '.py', '.js', '.ts', '.tsx', '.jsx', '.css', '.sql', '.sh', '.bat', '.ini', '.cfg', '.conf', '.env', '.rst', '.tex'}
    
    file_contents = []
    skipped = []
    
    for file in files:
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()
        
        if ext not in TEXT_EXTENSIONS:
            skipped.append(filename)
            continue
        
        try:
            raw = await file.read()
            content = raw.decode('utf-8', errors='ignore')[:10000]
            file_contents.append({"name": filename, "content": content})
        except Exception as e:
            logger.warning(f"Upload read error {filename}: {e}")
            skipped.append(filename)
    
    if not file_contents:
        detail = "テキストファイルが見つかりません。"
        if skipped:
            detail += f" スキップ: {', '.join(skipped)}。"
        detail += f" 対応拡張子: {', '.join(sorted(TEXT_EXTENSIONS))}"
        raise HTTPException(status_code=400, detail=detail)
    
    result = await _analyze_with_gemini(file_contents)
    if skipped:
        result["skipped_files"] = skipped
    return result


async def _analyze_with_gemini(file_contents: List[Dict[str, str]]) -> dict:
    """ファイル内容をGemini APIで分析し、マインドマップ構造を返す共通ロジック"""
    import json
    from google import genai as _genai
    from google.genai import types as _types

    # Web設定からAPIキーとモデルを取得
    api_key = api_settings.get_api_key()
    analysis_model = api_settings.get_analysis_model()

    if not api_key:
        raise HTTPException(status_code=400, detail="APIキーが設定されていません。設定画面からGemini APIキーを入力してください。")

    _client = _genai.Client(api_key=api_key)
    
    files_text = ""
    for fc in file_contents:
        files_text += f"\n--- File: {fc['name']} ---\n{fc['content'][:5000]}\n"
    
    # 学習済みルールの読み込み
    rules_section = ""
    rules_path = Path(__file__).parent.parent / "analysis_rules.json"
    if rules_path.exists():
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                saved_rules = json.load(f)
            if saved_rules.get("rules"):
                rules_text = "\n".join(f"- {r}" for r in saved_rules["rules"])
                rules_section = f"""

ユーザーの過去の修正から学習した追加ルール（これらを優先的に適用してください）:
{rules_text}"""
        except Exception as e:
            logger.warning(f"Failed to load analysis rules: {e}")
    
    prompt = f"""以下のテキストファイルの内容を分析し、キーコンセプトとその関連性をマインドマップ構造として抽出してください。

ファイル一覧:
{files_text}

以下のJSON形式で出力してください。要約や間引きを行わず、テキスト内のすべての重要な決定事項、依存関係、前提条件、リスクなどの要素を漏れなく個別のノードとして詳細に抽出してください。ノード数に上限はありません。可能な限り詳細なマインドマップツリーを生成してください:
{{
  "title": "マインドマップのタイトル",
  "nodes": [
    {{
      "id": "n1",
      "label": "コンセプト名",
      "description": "概要説明",
      "category": "カテゴリ名",
      "source_file": "元のファイル名"
    }}
  ],
  "edges": [
    {{
      "source": "n1",
      "target": "n2",
      "reason": "関連理由"
    }}
  ]
}}

重要なルール:
- 各ファイルの主要テーマをノードとして抽出
- ファイル間の関連性をエッジで表現
- categoryはファイル内容の分野（設計、管理、技術、データ等）を設定
- ルートノードは必ず id="root" で作成
- すべてのノードは直接または間接的にrootから到達可能であること
- JSONのみを出力（マークダウンやコメント不要）{rules_section}"""

    try:
        response = _client.models.generate_content(
            model=analysis_model,
            contents=prompt,
            config=_types.GenerateContentConfig(response_mime_type="application/json")
        )
        response_text = response.text.strip()
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from Gemini: {e}\nResponse: {response_text[:500]}")
        raise HTTPException(status_code=500, detail=f"AI応答のパースに失敗: {str(e)}")
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise HTTPException(status_code=500, detail=f"AI分析エラー: {str(e)}")
    
    CATEGORY_COLORS = {
        '設計': '#3b82f6', '管理': '#6b7280', '技術': '#ef4444',
        '分析': '#8b5cf6', 'データ': '#22c55e', '文書': '#f59e0b',
        '構造': '#ef4444', '意匠': '#3b82f6', '設備': '#22c55e',
    }
    DEFAULT_COLOR = '#6366f1'
    
    ai_nodes = result.get("nodes", [])
    ai_edges = result.get("edges", [])
    
    children_map: Dict[str, List[str]] = {}
    for e in ai_edges:
        src = e["source"]
        if src not in children_map:
            children_map[src] = []
        children_map[src].append(e["target"])
    
    node_ids = {n["id"] for n in ai_nodes}
    levels: Dict[str, int] = {}
    root_id = "root"
    if root_id not in node_ids:
        root_id = ai_nodes[0]["id"] if ai_nodes else "root"
    
    queue = [root_id]
    levels[root_id] = 0
    visited = {root_id}
    while queue:
        current = queue.pop(0)
        for child in children_map.get(current, []):
            if child not in visited and child in node_ids:
                levels[child] = levels[current] + 1
                visited.add(child)
                queue.append(child)
    
    max_level = max(levels.values()) if levels else 0
    for n in ai_nodes:
        if n["id"] not in levels:
            max_level += 1
            levels[n["id"]] = max_level
    
    level_counts: Dict[int, int] = {}
    X_GAP = 350
    Y_GAP = 120
    
    nodes_out = []
    for n in ai_nodes:
        level = levels.get(n["id"], 0)
        y_idx = level_counts.get(level, 0)
        level_counts[level] = y_idx + 1
        
        cat = n.get("category", "")
        
        nodes_out.append({
            "id": n["id"],
            "label": n["label"],
            "description": n.get("description", ""),
            "phase": n.get("source_file", "分析結果"),
            "category": cat,
            "checklist": [],
            "deliverables": [],
            "key_stakeholders": [],
            "position": {"x": level * X_GAP, "y": y_idx * Y_GAP},
            "status": "未着手",
            "is_custom": False,
        })
    
    edges_out = []
    for i, e in enumerate(ai_edges):
        if e["source"] in node_ids and e["target"] in node_ids:
            edges_out.append({
                "id": f"e_{e['source']}_{e['target']}",
                "source": e["source"],
                "target": e["target"],
                "type": "hard",
                "reason": e.get("reason", ""),
            })
    
    return {
        "title": result.get("title", "テキスト分析結果"),
        "nodes": nodes_out,
        "edges": edges_out,
        "source_files": [fc["name"] for fc in file_contents],
    }


@router.post("/fs/learn-rules")
async def learn_rules(request: dict):
    """オリジナルと編集後のマインドマップを比較し、分析ルールを学習・保存する"""
    import json
    from google import genai as _genai
    from config import GEMINI_API_KEY, PREVIEW_MODEL

    original_nodes = request.get("original_nodes", [])
    original_edges = request.get("original_edges", [])
    edited_nodes = request.get("edited_nodes", [])
    edited_edges = request.get("edited_edges", [])

    if not original_nodes and not edited_nodes:
        raise HTTPException(status_code=400, detail="ノードデータが必要です")

    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    _client = _genai.Client(api_key=GEMINI_API_KEY)

    # 差分を作りやすい形にシリアライズ
    orig_summary = json.dumps(
        {"nodes": [{"id": n["id"], "label": n["label"], "category": n.get("category","")} for n in original_nodes],
         "edges": [{"source": e["source"], "target": e["target"]} for e in original_edges]},
        ensure_ascii=False, indent=2)
    edit_summary = json.dumps(
        {"nodes": [{"id": n["id"], "label": n["label"], "category": n.get("category","")} for n in edited_nodes],
         "edges": [{"source": e["source"], "target": e["target"]} for e in edited_edges]},
        ensure_ascii=False, indent=2)

    prompt = f"""以下は、AIが生成したマインドマップ（オリジナル）と、ユーザーが手動で修正した結果（編集後）です。
差分を分析し、ユーザーの好み・修正パターンをルールとして抽出してください。

## オリジナル（AI生成）:
{orig_summary}

## 編集後（ユーザー修正）:
{edit_summary}

以下のJSON形式で、3〜10個程度のルールを出力してください:
{{
  "rules": [
    "ルール文（例: ノードのカテゴリ名は日本語で統一する）",
    "ルール文（例: ルートノードからの深さは3階層以内にする）"
  ]
}}

ルール抽出のポイント:
- ラベルの命名規則（日本語/英語、簡潔さ、専門用語の扱い）
- ノード数の増減傾向
- カテゴリの統合・分割・名称変更
- エッジの追加・削除パターン
- 階層構造の深さの好み
- 削除されたノードの特徴（不要と判断された情報）
- 追加されたノードの特徴（AIが見逃した重要な概念）
- JSONのみを出力"""

    try:
        response = _client.models.generate_content(model=PREVIEW_MODEL, contents=prompt)
        response_text = response.text.strip()

        if response_text.startswith("```"):
            lines = response_text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            response_text = "\n".join(json_lines)

        new_rules = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"Rule extraction parse error: {e}")
        raise HTTPException(status_code=500, detail=f"ルール抽出の解析に失敗: {str(e)}")
    except Exception as e:
        logger.error(f"Rule extraction API error: {e}")
        raise HTTPException(status_code=500, detail=f"ルール抽出エラー: {str(e)}")

    # 既存ルールとマージ
    rules_path = Path(__file__).parent.parent / "analysis_rules.json"
    existing_rules: List[str] = []
    if rules_path.exists():
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            existing_rules = existing_data.get("rules", [])
        except Exception:
            pass

    merged = existing_rules + new_rules.get("rules", [])
    # 重複除去（順序保持）
    seen = set()
    unique_rules = []
    for r in merged:
        if r not in seen:
            seen.add(r)
            unique_rules.append(r)

    # 保存
    with open(rules_path, 'w', encoding='utf-8') as f:
        json.dump({"rules": unique_rules}, f, ensure_ascii=False, indent=2)

    logger.info(f"Analysis rules updated: {len(unique_rules)} rules saved")

    return {
        "new_rules": new_rules.get("rules", []),
        "total_rules": len(unique_rules),
        "all_rules": unique_rules,
    }


@router.get("/fs/rules")
async def get_rules():
    """保存済み分析ルールを取得する"""
    import json
    rules_path = Path(__file__).parent.parent / "analysis_rules.json"
    if not rules_path.exists():
        return {"rules": [], "total": 0}
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {"rules": data.get("rules", []), "total": len(data.get("rules", []))}
    except Exception:
        return {"rules": [], "total": 0}


@router.put("/fs/rules")
async def update_rules(request: dict):
    """分析ルールを更新する（追加・編集・削除）"""
    import json
    rules_path = Path(__file__).parent.parent / "analysis_rules.json"
    new_rules = request.get("rules", [])
    
    # バリデーション: 文字列のリストであること
    if not isinstance(new_rules, list):
        raise HTTPException(status_code=400, detail="rules must be a list of strings")
    new_rules = [r.strip() for r in new_rules if isinstance(r, str) and r.strip()]
    
    # 保存
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    with open(rules_path, 'w', encoding='utf-8') as f:
        json.dump({"rules": new_rules}, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Analysis rules updated via UI: {len(new_rules)} rules")
    return {"rules": new_rules, "total": len(new_rules)}


@router.delete("/fs/rules")
async def clear_rules():
    """分析ルールをリセットする"""
    import json
    rules_path = Path(__file__).parent.parent / "analysis_rules.json"
    if rules_path.exists():
        rules_path.unlink()
    return {"message": "ルールをリセットしました"}


@router.post("/fs/export-md")
async def export_mindmap_md(request: dict):
    """マインドマップをMarkdownファイルとしてエクスポートする"""
    title = request.get("title", "マインドマップ")
    nodes = request.get("nodes", [])
    edges = request.get("edges", [])

    if not nodes:
        raise HTTPException(status_code=400, detail="ノードデータが必要です")

    # ノードIDマップ
    node_map = {n["id"]: n for n in nodes}

    # カテゴリごとにグルーピング
    categories: Dict[str, List[dict]] = {}
    for n in nodes:
        cat = n.get("category", "その他") or "その他"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(n)

    # エッジをソースごとにグルーピング
    edge_map: Dict[str, List[dict]] = {}
    for e in edges:
        src = e["source"]
        if src not in edge_map:
            edge_map[src] = []
        edge_map[src].append(e)

    # Markdown生成
    lines = [f"# {title}", ""]

    for cat, cat_nodes in categories.items():
        lines.append(f"## {cat}")
        lines.append("")
        for n in cat_nodes:
            label = n.get("label", n["id"])
            desc = n.get("description", "")
            phase = n.get("phase", "")
            lines.append(f"### {label}")
            if desc:
                lines.append(f"")
                lines.append(f"{desc}")
            if phase:
                lines.append(f"")
                lines.append(f"*出典: {phase}*")
            # このノードからのエッジ
            outgoing = edge_map.get(n["id"], [])
            if outgoing:
                lines.append("")
                lines.append("**関連:**")
                for e in outgoing:
                    target = node_map.get(e["target"], {})
                    target_label = target.get("label", e["target"])
                    reason = e.get("reason", "")
                    if reason:
                        lines.append(f"- → {target_label} — {reason}")
                    else:
                        lines.append(f"- → {target_label}")
            lines.append("")

    # 統計
    lines.append("---")
    lines.append(f"*ノード数: {len(nodes)} | エッジ数: {len(edges)} | カテゴリ数: {len(categories)}*")

    markdown = "\n".join(lines)

    return {"markdown": markdown, "title": title}

    return {"markdown": markdown, "title": title}


class AIActionRequest(BaseModel):
    action: str
    nodeId: str
    content: str
    context: Optional[Dict[str, Any]] = None


@router.post("/ai/action")
async def ai_action_endpoint(req: AIActionRequest):
    """AI Copilot Action Handler"""
    from google import genai as _genai
    import json

    # 1. Configuration
    api_key = api_settings.get_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key not configured")

    _client = _genai.Client(api_key=api_key)
    model_name = api_settings.get_analysis_model() or "gemini-2.0-flash"

    try:
        # 2. Handle Actions
        if req.action == "summarize":
            prompt = f"以下のテキストを要約してください。文脈: {req.context}\n\nテキスト: {req.content}"
            resp = _client.models.generate_content(model=model_name, contents=prompt)
            return {"text": resp.text.strip()}

        elif req.action == "expand":
            prompt = f"""
            あなたは建築・設計・プロジェクト管理の専門家のリサーチアシスタントです。
            ユーザーがマインドマップのノード「{req.content}」について情報を深めるべく、次の意思決定を行おうとしています。
            
            目的: このノードの意思決定を確実なものにするため「何を調べるべきか」「どういうキーワードでリサーチすべきか」「関係者や専門家に具体的に何を聞くべきか」という【リサーチプロンプト（調査指示書）】を5〜7件作成してください。
            単なるアイデアの羅列ではなく、具体的なアクションや調査行動につながる「問い」を重視してください。

            プロジェクト文脈: {req.context}
            
            出力フォーマット:
            Markdown形式のリストで出力してください。
            各項目には、リサーチの観点と、そのままコピーして使える具体的な質問文・検索クエリを含めてください。
            
            例:
            * **【〇〇の調査】**: 関連法令や基準を確認する
              * 検索キーワード例: `...`
              * 専門家への質問例: 「〜〜の場合、...はどうなりますか？」
            """
            resp = _client.models.generate_content(model=model_name, contents=prompt)
            return {"text": resp.text.strip()}

        elif req.action == "rag":
            # RAG implementation requires imports from root
            try:
                import sys
                import os
                
                # Add parent directory to path if not present (for accessing retriever.py from mindmap/router.py)
                # This handles cases where we are running from root but mindmap is treated as a package
                current_dir = os.path.dirname(os.path.abspath(__file__))
                parent_dir = os.path.dirname(current_dir)
                if parent_dir not in sys.path:
                    sys.path.append(parent_dir)

                # Try absolute imports (assuming running from root)
                try:
                    import retriever
                    import generator
                except ImportError:
                    # Try relative imports if loaded as a package
                    from .. import retriever
                    from .. import generator
                
                # 1. Search
                query = f"{req.content}に関連する重要な情報は？"
                search_results = retriever.search(query)
                
                # 2. Context
                rag_context = retriever.build_context(search_results)
                
                # 3. Generate
                answer = generator.generate_answer(query, rag_context, [])
                return {"text": answer}
                
            except ImportError as e:
                # Fallback if RAG modules not available
                logger.warning(f"RAG modules not found ({e}), falling back to pure LLM")
                prompt = f"以下のトピックについて、一般的知識に基づいて解説してください: {req.content}"
                resp = _client.models.generate_content(model=model_name, contents=prompt)
                return {"text": "【注意: RAGモジュール利用不可のため、一般知識回答です】\n" + resp.text.strip()}

        elif req.action == "investigate":
            # Research Assistant: Generate verification items
            prompt = f"""
            あなたは建築のプロフェッショナルです。
            以下のノードについて、設計・施工・管理の観点から「確認すべきこと」「調査すべきこと」「検討すべきリスク」をリストアップしてください。
            
            対象: {req.content}
            プロジェクト文脈: {req.context}
            
            出力フォーマット:
            Markdown形式のチェックリストで出力してください。
            重要な項目は太字にしてください。
            カテゴリごとに分けて記述してください（例: ### 法規, ### 施工, ### コスト）。
            """
            resp = _client.models.generate_content(model=model_name, contents=prompt)
            return {"text": resp.text.strip()}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    except Exception as e:
        logger.error(f"AI Action Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AutoLinkRequest(BaseModel):
    nodeId: str
    label: str
    description: Optional[str] = ""
    projectContext: Optional[str] = ""

@router.post("/ai/auto-link")
async def ai_auto_link_endpoint(req: AutoLinkRequest):
    """
    バックグラウンドでノードの内容に関連する知識を検索し、リンク候補を返す
    """
    try:
        # Check API key configuration
        api_key = api_settings.get_api_key()
        if not api_key:
            raise HTTPException(status_code=400, detail="API Key not configured")

        # Configure Generative AI
        from google import genai as _genai
        _client = _genai.Client(api_key=api_key)

        # 1. Extract Keywords using Gemini (lightweight model)
        model_name = api_settings.get_analysis_model() or "gemini-2.0-flash"

        prompt = f"""
        以下のノード情報から、建築知識データベースを検索するための重要なキーワードを3つ抽出してください。
        JSON形式で `keywords` 配列として返してください。

        ノードラベル: {req.label}
        説明: {req.description}
        プロジェクト文脈: {req.projectContext}
        """
        
        # Use JSON generation if possible, or parse text
        try:
            resp = _client.models.generate_content(model=model_name, contents=prompt)
            text = resp.text.strip()
            # Cleanup code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
            if text.startswith("json"):
                text = text[4:]
            
            import json
            import re
            # Try direct JSON parse first
            try:
                keywords = json.loads(text).get("keywords", [])
            except:
                # Fallback regex
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    keywords = json.loads(json_match.group(0)).get("keywords", [])
                else:
                    keywords = [req.label]
        except Exception as e:
            logger.warning(f"Keyword extraction failed: {e}")
            keywords = [req.label]

        # 2. Search RAG (Retriever)
        query = " ".join(keywords)
        results = []
        
        try:
            import sys
            import os
            
            # Setup path for imports (same as ai_action_endpoint)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            if parent_dir not in sys.path:
                sys.path.append(parent_dir)

            try:
                import retriever
            except ImportError:
                from .. import retriever
            
            # Perform search
            search_results = retriever.search(query, top_k=3)
            
            # Format results
            for res in search_results:
                results.append({
                    "id": res.get("id", "unknown"),
                    "source": res.get("source", "Unknown Source"),
                    "content": res.get("content", "")[:200] + "...", # Truncate for preview
                    "relevance": res.get("distance", 0.0), # or score
                    "full_content": res.get("content", "")
                })

        except ImportError as e:
            logger.error(f"RAG module import failed: {e}")
        except Exception as e:
            logger.error(f"RAG search failed: {e}")

        return {
            "nodeId": req.nodeId,
            "keywords": keywords,
            "results": results
        }

    except Exception as e:
        logger.error(f"Auto-link error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/action")
async def ai_action(req: AIActionRequest):
    """マインドマップ上のAIアクション（要約・拡張・RAG補完）を実行する"""
    import json
    from google import genai as _genai
    from google.genai import types as _types

    api_key = api_settings.get_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="APIキーが設定されていません。設定画面からGemini APIキーを入力してください。")

    _client = _genai.Client(api_key=api_key)
    _model_name = "gemini-2.0-flash"

    label = req.content or req.nodeId
    action = req.action

    try:
        if action == "summarize":
            prompt = f"あなたは建築プロジェクトのPMです。\n指定されたプロセスマップのノード「{label}」について、一般的にどのような作業が求められるか、重要なポイントを3点程度で簡潔に要約してください。"
            res = _client.models.generate_content(model=_model_name, contents=prompt)
            return {"text": f"【AI要約】\n{res.text}"}

        elif action == "expand":
            prompt = f'''あなたはチーフアーキテクトです。
プロセスマップのノード「{label}」をさらに細分化する場合、どのようなサブタスクや具体的な検討事項（子ノード）が考えられますか？
以下のJSON形式で3〜5個出力してください。

{{
  "children": [
    {{
      "label": "サブタスク名",
      "phase": "フェーズ名（例: 基本設計, 実施設計, 施工など）",
      "category": "カテゴリ名（例: 意匠, 構造, 設備, 管理など）"
    }}
  ]
}}'''
            res = _client.models.generate_content(
                model=_model_name, contents=prompt,
                config=_types.GenerateContentConfig(response_mime_type="application/json")
            )
            data = json.loads(res.text)
            return data

        elif action == "rag":
            prompt = f"あなたは熟練の建築技術者です。\nプロセスマップのノード「{label}」に関連して、過去のプロジェクトで起きがちなトラブル、注意すべき法規制、または参考となるベストプラクティスを簡潔に教えてください。"
            res = _client.models.generate_content(model=_model_name, contents=prompt)
            return {"text": f"【RAG/AI知見補完】\n{res.text}"}
            
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
            
    except Exception as e:
        logger.error(f"AI Action Error: {e}")
        raise HTTPException(status_code=500, detail=f"AIアクション実行中にエラーが発生しました: {str(e)}")
