"""
プロジェクト永続化ストア（SQLite）— v2 差分保存方式
テンプレートIDのみ保存し、変更は差分（delta）として記録する。
表示時にテンプレート + deltaをマージして返却する。
"""
import json
import sqlite3
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from .models import ProcessNode, Edge, Position, EdgeType, NodeStatus, MindmapTemplate

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "projects.db"


@contextmanager
def get_db():
    """DB接続コンテキストマネージャ"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction failed: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def init_db():
    """テーブル作成（v2 delta方式）"""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                template_id TEXT NOT NULL,
                building_type TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                technical_conditions TEXT DEFAULT '',
                legal_requirements TEXT DEFAULT '',
                layer_b_project_id TEXT DEFAULT '',
                gap_check_history TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS project_deltas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                delta_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_deltas_project
                ON project_deltas(project_id);

            CREATE TABLE IF NOT EXISTS undo_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
        """)

        # v1テーブルが残っていれば削除
        for old_table in ['project_nodes', 'project_edges']:
            try:
                conn.execute(f"DROP TABLE IF EXISTS {old_table}")
            except sqlite3.Error as e:
                logger.debug(f"Failed to drop old table {old_table}: {e}")

    logger.info("Project DB initialized (v2 delta mode)")


# --- Project CRUD ---

def create_project(name: str, template: MindmapTemplate) -> str:
    """テンプレートからプロジェクトをフォーク（差分方式：テンプレートIDのみ保存）"""
    project_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()

    template_id = template.meta.id if template.meta else template.id

    with get_db() as conn:
        conn.execute(
            """INSERT INTO projects (id, name, description, template_id, building_type, status, created_at, updated_at, technical_conditions, legal_requirements, layer_b_project_id, gap_check_history)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project_id, name, f"{template.name}からフォーク", template_id, "", "active", now, now, "", "", "", "[]")
        )

    logger.info(f"Project created: {project_id} (template={template_id}, delta mode)")
    return project_id


def list_projects() -> List[Dict[str, Any]]:
    """プロジェクト一覧（進捗情報付き）"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()

        result = []
        for r in rows:
            proj = dict(r)
            # delta数をnode_countの代わりに返す
            delta_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM project_deltas WHERE project_id = ?",
                (proj['id'],)
            ).fetchone()['cnt']
            proj['delta_count'] = delta_count
            proj['node_count'] = 0  # 後方互換
            
            if 'gap_check_history' in proj and isinstance(proj['gap_check_history'], str):
                try:
                    proj['gap_check_history'] = json.loads(proj['gap_check_history'])
                except:
                    proj['gap_check_history'] = []
                    
            result.append(proj)
        return result


def get_project_data(project_id: str) -> Optional[Dict[str, Any]]:
    """プロジェクトの全データを取得（テンプレート + delta マージ）"""
    with get_db() as conn:
        proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not proj:
            return None

        deltas = conn.execute(
            "SELECT * FROM project_deltas WHERE project_id = ? ORDER BY id ASC",
            (project_id,)
        ).fetchall()

        proj_dict = dict(proj)
        if 'gap_check_history' in proj_dict and isinstance(proj_dict['gap_check_history'], str):
            try:
                proj_dict['gap_check_history'] = json.loads(proj_dict['gap_check_history'])
            except:
                proj_dict['gap_check_history'] = []

        return {
            "project": proj_dict,
            "deltas": [dict(d) for d in deltas],
        }


def get_project_with_merged_data(project_id: str, template: MindmapTemplate) -> Optional[Dict[str, Any]]:
    """テンプレートとdeltaをマージした完全なプロジェクトデータを取得"""
    data = get_project_data(project_id)
    if not data:
        return None

    # テンプレートのノード/エッジをコピー
    nodes = {}
    for n in template.nodes:
        node_dict = _node_to_dict(n)
        node_dict['source_type'] = 'template' # Task-4: Tag as template
        nodes[n.id] = node_dict
        
    edges = {e.id: _edge_to_dict(e) for e in template.edges}

    # deltaを適用
    for delta in data.get("deltas", []):
        dtype = delta["delta_type"]
        target = delta["target_id"]
        payload = json.loads(delta["data_json"])

        if dtype == "modify_node":
            if target in nodes:
                nodes[target].update(payload)
        elif dtype == "add_node":
            nodes[target] = payload
        elif dtype == "remove_node":
            nodes.pop(target, None)
            # 関連エッジも削除
            edges = {eid: e for eid, e in edges.items()
                     if e.get("source") != target and e.get("target") != target}
        elif dtype == "modify_edge":
            if target in edges:
                edges[target].update(payload)
        elif dtype == "add_edge":
            edges[target] = payload
        elif dtype == "remove_edge":
            edges.pop(target, None)

    # ProcessNode/Edgeに変換
    result_nodes = []
    for n in nodes.values():
        checklist = n.get('checklist', [])
        deliverables = n.get('deliverables', [])
        
        # 簡易なdone判定 (dictに'done'が含まれるか、文字列に[x]が含まれる等)
        done_count = 0
        for item in checklist:
            if isinstance(item, dict) and item.get('done'):
                done_count += 1
            elif isinstance(item, str) and ('[x]' in item.lower() or '☑' in item):
                done_count += 1

        result_nodes.append(ProcessNode(
            id=n['id'],
            label=n.get('label', ''),
            description=n.get('description', ''),
            phase=n.get('phase', ''),
            category=n.get('category', ''),
            checklist=checklist,
            deliverables=deliverables,
            key_stakeholders=n.get('key_stakeholders', []),
            position=Position(x=n.get('pos_x', n.get('position', {}).get('x', 0)),
                              y=n.get('pos_y', n.get('position', {}).get('y', 0))),
            is_custom=n.get('is_custom', False),
            status=n.get('status', '未着手'),
            chatHistory=n.get('chatHistory', []),
            ragResults=n.get('ragResults', []),
            source_type=n.get('source_type', 'manual'),
            checklist_total=len(checklist),
            checklist_done=done_count,
            deliverables_count=len(deliverables),
        ))

    result_edges = []
    for e in edges.values():
        result_edges.append(Edge(
            id=e['id'],
            source=e['source'],
            target=e['target'],
            type=e.get('type', 'hard'),
            reason=e.get('reason', ''),
        ))

    return {
        "project": data["project"],
        "nodes": result_nodes,
        "edges": result_edges,
    }


def delete_project(project_id: str) -> bool:
    """プロジェクト削除"""
    with get_db() as conn:
        result = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return result.rowcount > 0


def update_project_context(project_id: str, updates: Dict[str, Any]) -> bool:
    """プロジェクトの文脈（前提条件等）を更新"""
    allowed = {'technical_conditions', 'legal_requirements'}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        return False
        
    set_clause = ", ".join([f"{k} = ?" for k in filtered.keys()])
    values = list(filtered.values()) + [project_id]
    
    with get_db() as conn:
        result = conn.execute(f"UPDATE projects SET {set_clause}, updated_at = ? WHERE id = ?", values[:-1] + [datetime.now(timezone.utc).isoformat(), project_id])
        return result.rowcount > 0


def update_gap_check_history(project_id: str, history_item: Dict[str, Any]) -> bool:
    """Gap Checkの履歴を追加"""
    with get_db() as conn:
        proj = conn.execute("SELECT gap_check_history FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not proj:
            return False
            
        history = []
        if proj['gap_check_history']:
            try:
                history = json.loads(proj['gap_check_history'])
            except:
                pass
                
        # 履歴ID付与
        if 'id' not in history_item:
            history_item['id'] = str(uuid.uuid4())[:8]
        history_item['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        history.append(history_item)
        
        conn.execute("UPDATE projects SET gap_check_history = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(history, ensure_ascii=False), datetime.now(timezone.utc).isoformat(), project_id))
        return True


def detect_structural_issues(project_id: str, template: MindmapTemplate) -> Dict[str, List[Dict[str, Any]]]:
    """マップ構造の検証（orphan, dead-end, root判定）"""
    merged = get_project_with_merged_data(project_id, template)
    if not merged:
        return {"orphans": [], "dead_ends": [], "roots": []}

    nodes = {n.id: n for n in merged["nodes"]}
    edges = merged["edges"]
    
    in_degree = {nid: 0 for nid in nodes}
    out_degree = {nid: 0 for nid in nodes}
    
    for edge in edges:
        if edge.target in in_degree:
            in_degree[edge.target] += 1
        if edge.source in out_degree:
            out_degree[edge.source] += 1
            
    orphans = []
    dead_ends = []
    roots = []
    
    for nid, node in nodes.items():
        ind = in_degree[nid]
        outd = out_degree[nid]
        
        node_info = {"id": nid, "label": node.label, "phase": node.phase}
        
        if ind == 0 and outd == 0:
            orphans.append(node_info)
        elif ind == 0 and outd > 0:
            roots.append(node_info)
        elif ind > 0 and outd == 0:
            dead_ends.append(node_info)
            
    return {
        "orphans": orphans,
        "dead_ends": dead_ends,
        "roots": roots
    }


def get_progress(project_id: str, template: MindmapTemplate) -> Dict[str, Any]:
    """プロジェクトの進捗を計算"""
    merged = get_project_with_merged_data(project_id, template)
    if not merged:
        return {"total": 0, "completed": 0, "in_progress": 0, "percent": 0}

    nodes = merged["nodes"]
    total = len(nodes)
    completed = sum(1 for n in nodes if n.status == NodeStatus.COMPLETED)
    in_progress = sum(1 for n in nodes if n.status == NodeStatus.IN_PROGRESS)

    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "percent": round(completed / total * 100) if total > 0 else 0,
    }


def get_next_actions(project_id: str, template: MindmapTemplate) -> List[Dict[str, Any]]:
    """依存が全て解決済みで、まだ未着手のノードを取得"""
    merged = get_project_with_merged_data(project_id, template)
    if not merged:
        return []

    nodes = {n.id: n for n in merged["nodes"]}
    edges = merged["edges"]

    # 各ノードへの必須依存（hard）の source を集約
    deps: Dict[str, List[str]] = {nid: [] for nid in nodes}
    for edge in edges:
        if edge.type == EdgeType.HARD:
            if edge.target in deps:
                deps[edge.target].append(edge.source)

    actions = []
    for nid, node in nodes.items():
        if node.status != NodeStatus.NOT_STARTED:
            continue
        # 全ての依存先が「決定済み」かチェック
        all_resolved = all(
            nodes.get(dep_id) and nodes[dep_id].status == NodeStatus.COMPLETED
            for dep_id in deps.get(nid, [])
        )
        if all_resolved:
            actions.append({
                "node_id": nid,
                "label": node.label,
                "phase": node.phase,
                "category": node.category,
                "dep_count": len(deps.get(nid, [])),
            })

    return actions


# --- Delta Operations ---

def _add_delta(conn, project_id: str, delta_type: str, target_id: str, data: Dict[str, Any]):
    """deltaレコードを追加"""
    conn.execute(
        """INSERT INTO project_deltas (project_id, delta_type, target_id, data_json, created_at)
           VALUES (?,?,?,?,?)""",
        (project_id, delta_type, target_id, json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat())
    )


def update_node(project_id: str, node_id: str, updates: Dict[str, Any]) -> bool:
    """ノードを更新（差分として記録）"""
    allowed = {'label', 'description', 'phase', 'category', 'status', 'pos_x', 'pos_y',
               'checklist', 'deliverables', 'key_stakeholders', 'notes', 'chatHistory', 'ragResults'}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        return False

    with get_db() as conn:
        _add_delta(conn, project_id, "modify_node", node_id, filtered)
        _record_undo(conn, project_id, 'modify_node', {'target_id': node_id, 'data': filtered})
        _touch_project(conn, project_id)
        return True


def add_node(project_id: str, node_data: Dict[str, Any]) -> str:
    """カスタムノードを追加（差分として記録）"""
    node_id = node_data.get('id', f"custom_{uuid.uuid4().hex[:6]}")
    node_data['id'] = node_id
    node_data['is_custom'] = True

    with get_db() as conn:
        _add_delta(conn, project_id, "add_node", node_id, node_data)
        _record_undo(conn, project_id, 'add_node', {'target_id': node_id})
        _touch_project(conn, project_id)

    return node_id


def delete_node(project_id: str, node_id: str) -> bool:
    """ノードを削除（差分として記録）"""
    with get_db() as conn:
        _add_delta(conn, project_id, "remove_node", node_id, {})
        _record_undo(conn, project_id, 'remove_node', {'target_id': node_id})
        _touch_project(conn, project_id)
        return True


def add_edge(project_id: str, edge_data: Dict[str, Any]) -> str:
    """エッジを追加（差分として記録）"""
    edge_id = edge_data.get('id', f"e_{uuid.uuid4().hex[:6]}")
    edge_data['id'] = edge_id

    with get_db() as conn:
        _add_delta(conn, project_id, "add_edge", edge_id, edge_data)
        _record_undo(conn, project_id, 'add_edge', {'target_id': edge_id})
        _touch_project(conn, project_id)

    return edge_id


def delete_edge(project_id: str, edge_id: str) -> bool:
    """エッジを削除（差分として記録）"""
    with get_db() as conn:
        _add_delta(conn, project_id, "remove_edge", edge_id, {})
        _record_undo(conn, project_id, 'remove_edge', {'target_id': edge_id})
        _touch_project(conn, project_id)
        return True


def update_edge(project_id: str, edge_id: str, updates: Dict[str, Any]) -> bool:
    """エッジを更新（差分として記録）"""
    allowed = {'type', 'reason', 'source', 'target'}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        return False

    with get_db() as conn:
        _add_delta(conn, project_id, "modify_edge", edge_id, filtered)
        _record_undo(conn, project_id, 'modify_edge', {'target_id': edge_id, 'data': filtered})
        _touch_project(conn, project_id)
        return True


# --- Undo ---

def undo(project_id: str) -> Optional[Dict[str, Any]]:
    """最後の操作を元に戻す（最新のdeltaを削除）"""
    with get_db() as conn:
        last_action = conn.execute(
            "SELECT * FROM undo_history WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,)
        ).fetchone()
        if not last_action:
            return None

        action_type = last_action['action_type']
        action_data = json.loads(last_action['action_data'])
        target_id = action_data.get('target_id', '')

        # 対応するdeltaを削除（最新のもの）
        last_delta = conn.execute(
            """SELECT id FROM project_deltas
               WHERE project_id = ? AND target_id = ?
               ORDER BY id DESC LIMIT 1""",
            (project_id, target_id)
        ).fetchone()

        if last_delta:
            conn.execute("DELETE FROM project_deltas WHERE id = ?", (last_delta['id'],))

        conn.execute("DELETE FROM undo_history WHERE id = ?", (last_action['id'],))
        _touch_project(conn, project_id)
        return {"undone": action_type, "target_id": target_id}


# --- Helpers ---

def _touch_project(conn, project_id: str):
    """updated_atを更新"""
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?",
                 (datetime.now(timezone.utc).isoformat(), project_id)) # Modified


def _record_undo(conn, project_id: str, action_type: str, action_data: Dict):
    """undo操作を記録"""
    conn.execute(
        "INSERT INTO undo_history (project_id, action_type, action_data, created_at) VALUES (?,?,?,?)",
        (project_id, action_type, json.dumps(action_data, ensure_ascii=False), datetime.now(timezone.utc).isoformat())
    )


def _node_to_dict(node: ProcessNode) -> Dict[str, Any]:
    """ProcessNodeをdictに変換"""
    return {
        "id": node.id,
        "label": node.label,
        "description": node.description,
        "phase": node.phase,
        "category": node.category,
        "checklist": node.checklist,
        "deliverables": node.deliverables,
        "key_stakeholders": node.key_stakeholders,
        "pos_y": node.position.y,
        "is_custom": node.is_custom,
        "status": node.status.value if hasattr(node.status, 'value') else node.status,
        "chatHistory": node.chatHistory,
        "ragResults": node.ragResults,
        "source_type": getattr(node, 'source_type', 'manual'),
    }


def _edge_to_dict(edge: Edge) -> Dict[str, Any]:
    """Edgeをdictに変換"""
    return {
        "id": edge.id,
        "source": edge.source,
        "target": edge.target,
        "type": edge.type.value if hasattr(edge.type, 'value') else edge.type,
        "reason": edge.reason,
    }


# 起動時にDB初期化
init_db()
