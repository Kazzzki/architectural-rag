'use client';

import React, { useCallback, useEffect, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  NodeChange,
  applyNodeChanges,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import { authFetch } from '@/lib/api';
import { Issue, IssueEdge } from '@/lib/issue_types';
import IssueNodeComponent from './IssueNode';
import type { PriorityFilter } from './IssueFilterBar';

const NODE_TYPES = { issueNode: IssueNodeComponent };

const NODE_W = 220;
const NODE_H = 80;

function buildDagreLayout(
  nodes: Node[],
  edges: Edge[]
): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: 120 });

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } };
  });
}

interface IssueCausalGraphProps {
  issues: Issue[];
  edges: IssueEdge[];
  priorityFilter: PriorityFilter;
  onNodeClick: (issue: Issue) => void;
  onRefresh: () => void;
}

export default function IssueCausalGraph({
  issues,
  edges,
  priorityFilter,
  onNodeClick,
  onRefresh,
}: IssueCausalGraphProps) {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([]);
  const [rfEdges, setRfEdges] = useEdgesState([]);

  // 折りたたまれた子ノードのセットを計算
  const collapsedChildIds = useMemo(() => {
    const collapsed = new Set<string>();
    const collapsedIssuedIds = new Set(
      issues.filter((iss) => iss.is_collapsed === 1).map((iss) => iss.id)
    );
    // 折りたたまれたノードを原因(from_id)とするエッジの先(to_id)を非表示にする
    edges.forEach((e) => {
      if (collapsedIssuedIds.has(e.from_id)) {
        collapsed.add(e.to_id);
      }
    });
    return collapsed;
  }, [issues, edges]);

  // 表示対象 issue を計算
  const visibleIssues = useMemo(
    () => issues.filter((iss) => !collapsedChildIds.has(iss.id)),
    [issues, collapsedChildIds]
  );

  // 折りたたまれた親ごとの隠れ子数
  const hiddenChildCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    issues
      .filter((iss) => iss.is_collapsed === 1)
      .forEach((iss) => {
        const childCount = edges.filter((e) => e.from_id === iss.id).length;
        if (childCount > 0) counts[iss.id] = childCount;
      });
    return counts;
  }, [issues, edges]);

  useEffect(() => {
    const issueLookup = new Map(issues.map((iss) => [iss.id, iss]));
    const visibleIds = new Set(visibleIssues.map((iss) => iss.id));

    // priority に応じてノードを構築
    const nodes: Node[] = visibleIssues.map((iss) => {
      const isDimmed =
        (priorityFilter === 'critical' && iss.priority !== 'critical') ||
        (priorityFilter === 'normal_up' && iss.priority === 'minor');

      // minor を小さなグレードットとして表示
      if (isDimmed && iss.priority === 'minor') {
        return {
          id: iss.id,
          type: 'default',
          position: { x: iss.pos_x, y: iss.pos_y },
          data: { label: '' },
          style: {
            width: 12,
            height: 12,
            borderRadius: '50%',
            background: '#B4B2A9',
            border: 'none',
            padding: 0,
          },
        };
      }

      return {
        id: iss.id,
        type: 'issueNode',
        position: { x: iss.pos_x, y: iss.pos_y },
        data: {
          issue: iss,
          hiddenChildCount: hiddenChildCounts[iss.id] ?? 0,
          onClick: onNodeClick,
        },
      };
    });

    // 自動配置 (全ノードが pos_x=0 && pos_y=0 の場合のみ — 手動ドラッグ位置を保持するため)
    const needsLayout = nodes.length > 0 && nodes.every(
      (n) => n.position.x === 0 && n.position.y === 0
    );

    const visibleEdges: Edge[] = edges
      .filter((e) => visibleIds.has(e.from_id) && visibleIds.has(e.to_id))
      .map((e) => ({
        id: e.id,
        source: e.from_id,
        target: e.to_id,
        animated: e.confirmed === 0,
        style: e.confirmed === 1
          ? { stroke: '#E24B4A', strokeWidth: 2 }
          : { stroke: '#B4B2A9', strokeWidth: 1.5, strokeDasharray: '5 4' },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: e.confirmed === 1 ? '#E24B4A' : '#B4B2A9',
        },
      }));

    const finalNodes = needsLayout
      ? buildDagreLayout(nodes, visibleEdges)
      : nodes;

    setRfNodes(finalNodes);
    setRfEdges(visibleEdges);
  }, [issues, edges, priorityFilter, visibleIssues, hiddenChildCounts, onNodeClick]);

  const handleNodeDragStop = useCallback(
    async (_: React.MouseEvent, node: Node) => {
      try {
        await authFetch(`/api/issues/${node.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pos_x: node.position.x, pos_y: node.position.y }),
        });
      } catch (e) {
        console.error('pos save failed', e);
      }
    },
    []
  );

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        onNodesChange={onNodesChange}
        onNodeDragStop={handleNodeDragStop}
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <Background gap={16} color="#e5e7eb" />
        <Controls />
        <MiniMap
          className="hidden md:block"
          nodeColor={(n) => {
            const iss = issues.find((i) => i.id === n.id);
            if (!iss) return '#ccc';
            return iss.priority === 'critical' ? '#F7C1C1' : iss.priority === 'minor' ? '#F1EFE8' : '#B5D4F4';
          }}
        />
      </ReactFlow>
    </div>
  );
}
