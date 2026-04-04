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
import ChainRiskScanPanel from './ChainRiskScanPanel';
import type { PriorityFilter } from './IssueFilterBar';

// カテゴリラベル用カスタムノード
function CategoryLabelNode({ data }: { data: { label: string; color: string } }) {
  return (
    <div style={{
      fontSize: 13, fontWeight: 700, color: data.color,
      background: `${data.color}10`, borderLeft: `3px solid ${data.color}`,
      padding: '4px 10px', borderRadius: 4, userSelect: 'none', whiteSpace: 'nowrap',
    }}>
      {data.label}
    </div>
  );
}

const NODE_TYPES = { issueNode: IssueNodeComponent, categoryLabel: CategoryLabelNode };
const EDGE_TYPES = { deletable: DeletableEdge };

const NODE_W = 220;
const NODE_H = 80;

// カテゴリ別色定義
const CATEGORY_COLORS: Record<string, string> = {
  '工程': '#3b82f6',
  'コスト': '#f59e0b',
  '品質': '#22c55e',
  '安全': '#ef4444',
};

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

/**
 * マインドマップ風レイアウト: カテゴリ別に縦に並べ、各カテゴリ内は横展開。
 * カテゴリラベルノードも追加して返す。
 */
function buildMindmapLayout(nodes: Node[], edges: Edge[], issues: Issue[]): Node[] {
  // カテゴリ別にノードをグループ分け
  const categories = ['工程', 'コスト', '品質', '安全'];
  const groups: Record<string, Node[]> = {};
  const issueMap = new Map(issues.map((i) => [i.id, i]));

  for (const n of nodes) {
    const iss = issueMap.get(n.id);
    const cat = iss?.category || '工程';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(n);
  }

  // 全ノードを含むdagreレイアウト（カテゴリ間エッジも含む）
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', nodesep: 50, ranksep: 150 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  // dagreの結果を取得し、カテゴリ別にy方向オフセットを追加
  const result: Node[] = [];
  let yOffset = 0;
  const CATEGORY_GAP = 60;

  // カテゴリごとにdagreの結果を調整
  for (const cat of categories) {
    const catNodes = groups[cat];
    if (!catNodes || catNodes.length === 0) continue;

    const color = CATEGORY_COLORS[cat] || '#6b7280';

    // カテゴリ内のdagreによるy座標の範囲を計算
    let minY = Infinity, maxY = -Infinity;
    for (const n of catNodes) {
      const pos = g.node(n.id);
      if (pos.y - NODE_H / 2 < minY) minY = pos.y - NODE_H / 2;
      if (pos.y + NODE_H / 2 > maxY) maxY = pos.y + NODE_H / 2;
    }

    const categoryHeight = maxY - minY;

    // カテゴリラベルノード
    result.push({
      id: `cat-label-${cat}`,
      type: 'categoryLabel',
      position: { x: -120, y: yOffset + 10 },
      data: { label: cat, color },
      draggable: false,
      selectable: false,
      style: { zIndex: -1 },
    } as Node);

    // ノードを配置（dagreのx座標を保持、y座標をオフセット）
    for (const n of catNodes) {
      const pos = g.node(n.id);
      result.push({
        ...n,
        position: { x: pos.x - NODE_W / 2, y: yOffset + (pos.y - minY) },
      });
    }

    yOffset += categoryHeight + CATEGORY_GAP;
  }

  // 未分類ノード
  const placedIds = new Set(result.map((n) => n.id));
  const unplaced = nodes.filter((n) => !placedIds.has(n.id));
  if (unplaced.length > 0) {
    result.push({
      id: 'cat-label-other',
      type: 'categoryLabel',
      position: { x: -120, y: yOffset + 10 },
      data: { label: 'その他', color: '#6b7280' },
      draggable: false,
      selectable: false,
      style: { zIndex: -1 },
    } as Node);

    unplaced.forEach((n, i) => {
      const pos = g.node(n.id);
      if (pos) {
        result.push({ ...n, position: { x: pos.x - NODE_W / 2, y: yOffset + 40 } });
      } else {
        result.push({ ...n, position: { x: i * (NODE_W + 40), y: yOffset + 40 } });
      }
    });
  }

  return result;
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
  layoutMode?: 'graph' | 'mindmap';
}

function IssueCausalGraphInner({
  issues, edges, priorityFilter, selectedNodeIds,
  onNodeClick, onRefresh, onSelectionChange, onIssueUpdated, fitViewTrigger,
  layoutMode = 'graph',
}: IssueCausalGraphProps) {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([]);
  const [rfEdges, setRfEdges] = useEdgesState([]);
  const { fitView } = useReactFlow();
  const initialFitDone = useRef(false);

  // コンテキストメニュー
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; issue: Issue } | null>(null);
  const [chainRiskIssueId, setChainRiskIssueId] = useState<string | null>(null);

  // ギャップ検出
  const [gapEdges, setGapEdges] = useState<Edge[]>([]);
  const [gapLoading, setGapLoading] = useState(false);
  const [gapStats, setGapStats] = useState<{ nodes: number; edges: number; components: number } | null>(null);
  const projectName = issues[0]?.project_name;

  const runGapAnalysis = useCallback(async () => {
    if (!projectName || gapLoading) return;
    setGapLoading(true);
    try {
      const res = await authFetch(`/api/issues/graph-analysis?project_name=${encodeURIComponent(projectName)}`);
      const data = await res.json();
      setGapStats(data.stats || null);
      const newEdges: Edge[] = (data.gaps || []).flatMap((gap: any, gi: number) => {
        if (!gap.cluster_a?.[0] || !gap.cluster_b?.[0]) return [];
        return [{ id: `gap-${gi}`, source: gap.cluster_a[0], target: gap.cluster_b[0], type: 'default',
          animated: true, style: { stroke: '#F59E0B', strokeDasharray: '6 4', strokeWidth: 2 },
          label: gap.suggestion?.slice(0, 30) || 'ギャップ候補',
          labelStyle: { fontSize: 9, fill: '#92400E' }, labelBgStyle: { fill: '#FEF3C7', fillOpacity: 0.9 } }];
      });
      setGapEdges(newEdges);
    } catch { /* silent */ }
    finally { setGapLoading(false); }
  }, [projectName, gapLoading]);

  // issue Map for O(1) lookup (MiniMap最適化)
  const issueMap = useMemo(() => new Map(issues.map((i) => [i.id, i])), [issues]);

  // layoutMode 切り替え時に fitView を実行
  const prevLayoutMode = useRef(layoutMode);
  useEffect(() => {
    if (prevLayoutMode.current !== layoutMode) {
      prevLayoutMode.current = layoutMode;
      initialFitDone.current = false; // 再レイアウト後にfitViewをトリガー
    }
  }, [layoutMode]);

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
            // 「...」ボタンクリック時 — 画面中央にメニュー表示（ワールド座標ではなくビューポート座標）
            setContextMenu({ x: window.innerWidth / 2, y: window.innerHeight / 3, issue });
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
          data: {
            onDeleteEdge: handleDeleteEdge,
            onEdgeUpdated: onRefresh,
            label: e.label,
            relationType: e.relation_type,
          },
        };
      });

    // レイアウト切り替え: マインドマップモードは常に自動レイアウト
    let finalNodes: Node[];
    if (layoutMode === 'mindmap') {
      finalNodes = buildMindmapLayout(nodes, visibleEdges, visibleIssues);
    } else {
      finalNodes = needsLayout ? buildDagreLayout(nodes, visibleEdges) : nodes;
    }
    setRfNodes(finalNodes);
    setRfEdges([...visibleEdges, ...gapEdges]);

    if (finalNodes.length > 0 && !initialFitDone.current) {
      initialFitDone.current = true;
      setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50);
    }
  }, [issues, edges, priorityFilter, visibleIssues, hiddenChildCounts, issueIdsWithChildren, selectedSet, onNodeClick, handleCollapseToggle, handleDeleteEdge, onIssueUpdated, fitView, layoutMode, gapEdges]);

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

  // B1: Delete/Backspaceキーでノード削除
  const handleNodesDelete = useCallback(async (deletedNodes: Node[]) => {
    for (const node of deletedNodes) {
      if (node.id.startsWith('cat-label-')) continue; // カテゴリラベルは削除しない
      try {
        await authFetch(`/api/issues/${node.id}`, { method: 'DELETE' });
      } catch {}
    }
    onRefresh();
  }, [onRefresh]);

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
        onNodesDelete={handleNodesDelete}
        onPaneClick={handlePaneClick}
        deleteKeyCode={['Backspace', 'Delete']}
        selectionOnDrag
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={3}
        zoomOnPinch
        panOnScroll={false}
      >
        <Background gap={16} color="#e5e7eb" />
        {projectName && (
          <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 10, display: 'flex', gap: 4 }}>
            {gapEdges.length > 0 && (
              <button onClick={() => { setGapEdges([]); setGapStats(null); }}
                style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, background: '#FEF3C7', border: '1px solid #F59E0B', color: '#92400E', cursor: 'pointer' }}>
                ギャップ非表示
              </button>
            )}
            <button onClick={runGapAnalysis} disabled={gapLoading}
              style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, background: gapLoading ? '#F3F4F6' : '#EFF6FF', border: '1px solid #93C5FD', color: '#1D4ED8', cursor: gapLoading ? 'wait' : 'pointer' }}>
              {gapLoading ? '分析中...' : '🔍 ギャップ検出'}
            </button>
            {gapStats && <span style={{ fontSize: 10, color: '#6B7280', lineHeight: '28px' }}>{gapStats.components}グループ / {gapStats.nodes}ノード</span>}
          </div>
        )}
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
          onChainRiskScan={(issue) => { setChainRiskIssueId(issue.id); }}
        />
      )}

      {/* チェーンリスク分析パネル (D3) — Drawerと排他表示 */}
      {chainRiskIssueId && (
        <ChainRiskScanPanel
          issueId={chainRiskIssueId}
          onClose={() => setChainRiskIssueId(null)}
          onNodeHighlight={(id) => {
            // Find and select the node on the graph
            const node = rfNodes.find(n => n.id === id || n.id.startsWith(id));
            if (node) {
              onNodeClick(node.data?.issue);
            }
          }}
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
