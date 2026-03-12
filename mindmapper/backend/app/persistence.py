import json
import os
from typing import List, Dict, Any

def _get_data_path():
    # backend/app/persistence.py -> ../../data/mindmap.json
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "../../data/mindmap.json")

def load_graph() -> Dict[str, Any]:
    path = _get_data_path()
    if not os.path.exists(path):
        return {"nodes": [], "edges": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"nodes": [], "edges": []}

def save_graph(data: Dict[str, Any]):
    path = _get_data_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def update_user_decision(node_id: str, decision: str):
    data = load_graph()
    updated = False
    for node in data.get("nodes", []):
        if node["id"] == node_id:
            node["data"]["user_decision"] = decision
            node["data"]["is_user_edited"] = True
            updated = True
            break
    if updated:
        save_graph(data)
    return updated

def merge_ai_nodes(new_nodes: List[Dict[str, Any]]):
    current_data = load_graph()
    existing_map = {n["id"]: n for n in current_data.get("nodes", [])}
    
    final_nodes = []
    processed_ids = set()

    for new_node in new_nodes:
        nid = new_node["id"]
        processed_ids.add(nid)
        if nid in existing_map:
            existing_node = existing_map[nid]
            if existing_node["data"].get("is_user_edited"):
                new_node["data"]["user_decision"] = existing_node["data"].get("user_decision", "")
                new_node["data"]["is_user_edited"] = True
            final_nodes.append(new_node)
        else:
            final_nodes.append(new_node)
    
    # Keep existing nodes that were NOT in the new batch (append them)
    # Note: If we want to support deletion, we need smarter logic. 
    # For now, we only append/update, never delete old nodes from other files.
    for curr in current_data.get("nodes", []):
        if curr["id"] not in processed_ids:
            final_nodes.append(curr)
        
    current_data["nodes"] = final_nodes
    save_graph(current_data)
