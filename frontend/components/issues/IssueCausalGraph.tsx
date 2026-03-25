'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Connection,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  MarkerType,
  OnSelectionChangeParams,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import { authFetch } from '@/lib/api';
import { Issue, IssueEdge, EdgeRelationType } from '@/lib/issue_types';
import IssueNodeComponent from './IssueNode';
import DeletableEdge from './DeletableEdge';
import NodeContextMenu from './NodeContextMenu';
import type { PriorityFilter } from './IssueFilterBar';

const NODE_TYPES = { issueNode: IssueNodeComponent };
const EDGE_TYPES = { deletable: DeletableEdge };

const NODE_W = 220;
const NODE_H = 80;

// エッジ種類別スタイル
const EDGE_STYLES: Record<string, { stroke: string; strokeWidth: number; strokeDasharray?: string }> = {
  direct_cause: { stroke: '#E24B4A', strokeWidth: 2 },
  indirect_cause: { stroke: '#F4A261', strokeWidth: 1.5, strokeDasharray: '5 4' },
  correlation: { stroke: '#B4B2A9', strokeWidth: 1.5, strokeDasharray: '2 3' },
  countermeasure: { stroke: '#52B788', strokeWidth: 2 },
};

function buildDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
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
  selectedNodeIds: string[];
  onNodeClick: (issue: Issue) => void;
  onRefresh: () => void;
  onSelectionChange: (nodeIds: string[]) => void;
  onIssueUpdated: (updated: Issue) => void;
  fitViewTrigger?: number;
}

function IssueCausalGraphInner({
  issues, edges, priorityFilter, selectedNodeIds,
  onNodeClick, onRefresh, onSelectionChange, onIssueUpdated, fitViewTrigger,
}: IssueCausalGraphProps) {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([]);
  const [rfEdges, setRfEdges] = useEdgesState([]);
  const { fitView } = useReactFlow();
  const initialFitDone = useRef(false);

  // コンテキストメニュー
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; issue: Issue } | null>(null);

  // issue Map for O(1) lookup (MiniMap最適化)
  const issueMap = useMemo(() => new Map(issues.map((i) => [i.id, i])), [issues]);

  useEffect(() => {
    if (fitViewTrigger !== undefined && fitViewTrigger > 0) fitView({ padding: 0.2 });
  }, [fitViewTrigger, fitView]);

  const collapsedChildIds = useMemo(() => {
    const collapsed = new Set<string>();
    const collapsedIssuedIds = new Set(issues.filter((iss) => iss.is_collapsed === 1).map((iss) => iss.id));
    edges.forEach((e) => { if (collapsedIssuedIds.has(e.from_id)) collapsed.add(e.to_id); });
    return collapsed;
  }, [issues, edges]);

  const visibleIssues = useMemo(() => issues.filter((iss) => !collapsedChildIds.has(iss.id)), [issues, collapsedChildIds]);

  const hiddenChildCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    issues.filter((iss) => iss.is_collapsed === 1).forEach((iss) => {
      const childCount = edges.filter((e) => e.from_id === iss.id).length;
      if (childCount > 0) counts[iss.id] = childCount;
    });
    return counts;
  }, [issues, edges]);

  const issueIdsWithChildren = useMemo(() => new Set(edges.map((e) => e.from_id)), [edges]);
  const selectedSet = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds]);

  const handleDeleteEdge = useCallback(async (edgeId: string) => {
    try {
      await authFetch(`/api/issues/edges/${edgeId}`, { method: 'DELETE' });
      onRefresh();
    } catch (e) { console.error('edge delete failed', e); }
  }, [onRefresh]);

  const handleCollapseToggle = useCallback(async (issue: Issue) => {
    try {
      const res = await authFetch(`/api/issues/${issue.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_collapsed: issue.is_collapsed === 1 ? 0 : 1 }),
      });
      if (res.ok) onRefresh();
    } catch (e) { console.error('collapse toggle failed', e); }
  }, [onRefresh]);

  // コンテキストメニューアクション
  const handleStatusChange = useCallback(async (issue: Issue, status: string) => {
    try {
      const res = await authFetch(`/api/issues/${issue.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (res.ok) { onIssueUpdated(await res.json()); onRefresh(); }
    } catch {}
  }, [onRefresh, onIssueUpdated]);

  const handlePriorityChange = useCallback(async (issue: Issue, priority: string) => {
    try {
      const res = await authFetch(`/api/issues/${issue.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priority }),
      });
      if (res.ok) { onIssueUpdated(await res.json()); onRefresh(); }
    } catch {}
  }, [onRefresh, onIssueUpdated]);

  const handleDeleteIssue = useCallback(async (issue: Issue) => {
    try {
      await authFetch(`/api/issues/${issue.id}`, { method: 'DELETE' });
      onRefresh();
    } catch {}
  }, [onRefresh]);

  const handleDuplicate = useCallback(async (issue: Issue) => {
    try {
      await authFetch('/api/issues/capture', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: issue.title, project_name: issue.project_name, skip_ai: true }),
      });
      onRefresh();
    } catch {}
  }, [onRefresh]);

  useEffect(() => {
    const visibleIds = new Set(visibleIssues.map((iss) => iss.id));

    const nodes: Node[] = visibleIssues.map((iss) => {
      const isDimmed =
        (priorityFilter === 'critical' && iss.priority !== 'critical') ||
        (priorityFilter === 'normal_up' && iss.priority === 'minor');

      if (isDimmed && iss.priority === 'minor') {
        return {
          id: iss.id, type: 'default',
          position: { x: iss.pos_x, y: iss.pos_y },
          data: { label: '' },
          style: { width: 12, height: 12, borderRadius: '50%', background: '#B4B2A9', border: 'none', padding: 0 },
        };
      }

      return {
        id: iss.id, type: 'issueNode',
        position: { x: iss.pos_x, y: iss.pos_y },
        data: {
          issue: iss,
          hiddenChildCount: hiddenChildCounts[iss.id] ?? 0,
          hasChildren: issueIdsWithChildren.has(iss.id),
          isSelected: selectedSet.has(iss.id),
          onClick: onNodeClick,
          onCollapseToggle: handleCollapseToggle,
          onTitleUpdated: onIssueUpdated,
          onMemoUpdated: onIssueUpdated,
          onContextMenu: (issue: Issue) => {
            // 「...」ボタンクリック時 — ノード位置にメニュー表示
            setContextMenu({ x: iss.pos_x + NODE_W, y: iss.pos_y, issue });
          },
        },
      };
    });

    const needsLayout = nodes.length > 0 && nodes.every((n) => n.position.x === 0 && n.position.y === 0);

    const visibleEdges: Edge[] = edges
      .filter((e) => visibleIds.has(e.from_id) && visibleIds.has(e.to_id))
      .map((e) => {
        const relType = (e.relation_type || 'direct_cause') as string;
        const edgeStyle = e.confirmed === 1
          ? (EDGE_STYLES[relType] || EDGE_STYLES.direct_cause)
          : { stroke: '#B4B2A9', strokeWidth: 1.5, strokeDasharray: '5 4' };

        return {
          id: e.id, source: e.from_id, target: e.to_id,
          type: 'deletable',
          animated: e.confirmed === 0,
          style: edgeStyle,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: edgeStyle.stroke,
          },
          label: e.label || undefined,
          labelStyle: e.label ? { fontSize: 10, fill: '#666' } : undefined,
          data: { onDeleteEdge: handleDeleteEdge },
        };
      });

    const finalNodes = needsLayout ? buildDagreLayout(nodes, visibleEdges) : nodes;
    setRfNodes(finalNodes);
    setRfEdges(visibleEdges);

    if (finalNodes.length > 0 && !initialFitDone.current) {
      initialFitDone.current = true;
      setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50);
    }
  }, [issues, edges, priorityFilter, visibleIssues, hiddenChildCounts, issueIdsWithChildren, selectedSet, onNodeClick, handleCollapseToggle, handleDeleteEdge, onIssueUpdated, fitView]);

  const handleNodeDragStop = useCallback(async (_: React.MouseEvent, node: Node) => {
    try {
      await authFetch(`/api/issues/${node.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pos_x: node.position.x, pos_y: node.position.y }),
      });
    } catch (e) { console.error('pos save failed', e); }
  }, []);

  const handleConnect = useCallback(async (connection: Connection) => {
    if (!connection.source || !connection.target) return;
    const duplicate = edges.some((e) => e.from_id === connection.source && e.to_id === connection.target);
    if (duplicate) return;
    try {
      await authFetch('/api/issues/edges/confirm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_id: connection.source, to_id: connection.target, confirmed: true }),
      });
      onRefresh();
    } catch (e) { console.error('connect failed', e); }
  }, [edges, onRefresh]);

  const handleContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault();
    const issue = issueMap.get(node.id);
    if (issue) setContextMenu({ x: event.clientX, y: event.clientY, issue });
  }, [issueMap]);

  const handleSelectionChange = useCallback((params: OnSelectionChangeParams) => {
    const nodeIds = params.nodes.map((n) => n.id);
    onSelectionChange(nodeIds);
  }, [onSelectionChange]);

  const handlePaneClick = useCallback(() => {
    setContextMenu(null);
  }, []);

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodesChange={onNodesChange}
        onNodeDragStop={handleNodeDragStop}
        onConnect={handleConnect}
        onNodeContextMenu={handleContextMenu}
        onSelectionChange={handleSelectionChange}
        onPaneClick={handlePaneClick}
        selectionOnDrag
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={3}
        zoomOnPinch
        panOnScroll={false}
      >
        <Background gap={16} color="#e5e7eb" />
        <div className="hidden md:block"><Controls /></div>
        <div className="hidden md:block">
          <MiniMap nodeColor={(n) => {
            const iss = issueMap.get(n.id);
            if (!iss) return '#ccc';
            return iss.priority === 'critical' ? '#F7C1C1' : iss.priority === 'minor' ? '#F1EFE8' : '#B5D4F4';
          }} />
        </div>
      </ReactFlow>

      {/* エッジ凡例 */}
      <div className="hidden md:block absolute bottom-2 left-2 bg-white/90 border border-gray-200 rounded-lg px-3 py-2 text-[10px] space-y-1 z-10">
        {[
          { label: '直接原因', color: '#E24B4A', dash: '' },
          { label: '間接原因', color: '#F4A261', dash: '5 4' },
          { label: '相関', color: '#B4B2A9', dash: '2 3' },
          { label: '対策', color: '#52B788', dash: '' },
        ].map((l) => (
          <div key={l.label} className="flex items-center gap-1.5">
            <svg width="20" height="6"><line x1="0" y1="3" x2="20" y2="3" stroke={l.color} strokeWidth="2" strokeDasharray={l.dash} /></svg>
            <span className="text-gray-600">{l.label}</span>
          </div>
        ))}
      </div>

      {/* コンテキストメニュー */}
      {contextMenu && (
        <NodeContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          issue={contextMenu.issue}
          onClose={() => setContextMenu(null)}
          onStatusChange={handleStatusChange}
          onPriorityChange={handlePriorityChange}
          onDelete={handleDeleteIssue}
          onDuplicate={handleDuplicate}
          onStartEdge={() => {}}
          onAIInvestigate={(issue) => onNodeClick(issue)}
          onOpenMemo={(issue) => onNodeClick(issue)}
        />
      )}
    </div>
  );
}

export default function IssueCausalGraph(props: IssueCausalGraphProps) {
  return (
    <ReactFlowProvider>
      <IssueCausalGraphInner {...props} />
    </ReactFlowProvider>
  );
}
