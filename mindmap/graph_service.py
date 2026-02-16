"""
グラフ探索ロジック（逆引きツリー、クリティカルパス、トポロジカルソート）
"""
from typing import List, Dict, Set, Tuple
from collections import defaultdict, deque

from .models import ProcessNode, Edge, MindmapTemplate, ReverseTreeResponse


class GraphService:
    """テンプレートのノード/エッジに対してグラフ操作を行う"""

    def __init__(self, template: MindmapTemplate):
        self.template = template
        self._node_map: Dict[str, ProcessNode] = {n.id: n for n in template.nodes}
        # 正方向: source -> [target, ...]
        self._forward: Dict[str, List[str]] = defaultdict(list)
        # 逆方向: target -> [source, ...]
        self._backward: Dict[str, List[str]] = defaultdict(list)
        # エッジマップ: (source, target) -> Edge
        self._edge_map: Dict[Tuple[str, str], Edge] = {}

        for edge in template.edges:
            self._forward[edge.source].append(edge.target)
            self._backward[edge.target].append(edge.source)
            self._edge_map[(edge.source, edge.target)] = edge

    def get_reverse_tree(self, goal_node_id: str) -> ReverseTreeResponse:
        """
        ゴールノードから逆方向にたどり、すべての先行ノードを取得する。
        BFS で探索し、到達可能なサブグラフを返す。
        """
        if goal_node_id not in self._node_map:
            raise ValueError(f"Node not found: {goal_node_id}")

        visited: Set[str] = set()
        queue = deque([goal_node_id])
        visited.add(goal_node_id)

        while queue:
            current = queue.popleft()
            for predecessor in self._backward.get(current, []):
                if predecessor not in visited:
                    visited.add(predecessor)
                    queue.append(predecessor)

        # サブグラフのノードとエッジを抽出
        sub_nodes = [self._node_map[nid] for nid in visited if nid in self._node_map]
        sub_edges = [
            edge for edge in self.template.edges
            if edge.source in visited and edge.target in visited
        ]

        # トポロジカルソート（サブグラフ内）
        path_order = self._topological_sort_subset(visited)

        return ReverseTreeResponse(
            goal_node_id=goal_node_id,
            nodes=sub_nodes,
            edges=sub_edges,
            path_order=path_order,
        )

    def get_critical_path(self, from_id: str, to_id: str) -> List[str]:
        """
        from_id から to_id への最長パス（クリティカルパス）を求める。
        DAG 前提なので DP で解ける。
        """
        if from_id not in self._node_map or to_id not in self._node_map:
            raise ValueError("Node not found")

        # BFS/DFS + メモ化で最長パスを探索
        memo: Dict[str, List[str]] = {}

        def dfs(current: str) -> List[str]:
            if current == to_id:
                return [current]
            if current in memo:
                return memo[current]

            best_path: List[str] = []
            for successor in self._forward.get(current, []):
                sub_path = dfs(successor)
                if sub_path and len(sub_path) > len(best_path):
                    best_path = sub_path

            if best_path:
                memo[current] = [current] + best_path
            else:
                memo[current] = []
            return memo[current]

        return dfs(from_id)

    def _topological_sort_subset(self, node_ids: Set[str]) -> List[str]:
        """サブグラフ内のトポロジカルソート（Kahnのアルゴリズム）"""
        # サブグラフの入次数を計算
        in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
        sub_forward: Dict[str, List[str]] = defaultdict(list)

        for edge in self.template.edges:
            if edge.source in node_ids and edge.target in node_ids:
                in_degree[edge.target] = in_degree.get(edge.target, 0) + 1
                sub_forward[edge.source].append(edge.target)

        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        result: List[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)
            for successor in sub_forward.get(current, []):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        return result

    def topological_sort(self) -> List[str]:
        """全ノードのトポロジカルソート"""
        all_ids = set(self._node_map.keys())
        return self._topological_sort_subset(all_ids)
