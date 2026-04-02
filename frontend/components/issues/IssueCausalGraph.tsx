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
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import { authFetch } from '@/lib/api';
import { Issue, IssueEdge, CaptureResponse } from '@/lib/issue_types';
import IssueNodeComponent from './IssueNode';
import DeletableEdge from './DeletableEdge';
import ConfirmDialog from './ConfirmDialog';
import type { PriorityFilter } from './IssueFilterBar';
import { Plus } from 'lucide-react';

const NODE_TYPES = { issueNode: IssueNodeComponent };
const EDGE_TYPES = { deletable: DeletableEdge };

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

/** 既存ノード群の右側に新規ノードの位置を計算 */
function computeNewNodePosition(existingNodes: Node[]): { x: number; y: number } {
  if (existingNodes.length === 0) return { x: 0, y: 0 };
  let maxX = -Infinity;
  let avgY = 0;
  for (const n of existingNodes) {
    if (n.position.x > maxX) maxX = n.position.x;
    avgY += n.position.y;
  }
  avgY /= existingNodes.length;
  return { x: maxX + NODE_W + 80, y: avgY };
}

interface IssueCausalGraphProps {
  issues: Issue[];
  edges: IssueEdge[];
  priorityFilter: PriorityFilter;
  onNodeClick: (issue: Issue) => void;
  onRefresh: () => void;
  fitViewTrigger?: number;
  /** Phase 2: direct node creation */
  projectName?: string;
  onIssueAdded?: (resp: CaptureResponse) => void;
}

function IssueCausalGraphInner({
  issues,
  edges,
  priorityFilter,
  onNodeClick,
  onRefresh,
  fitViewTrigger,
  projectName,
  onIssueAdded,
}: IssueCausalGraphProps) {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([]);
  const { fitView, screenToFlowPosition, flowToScreenPosition } = useReactFlow();
  const initialFitDone = useRef(false);

  // --- Note expansion ---
  const [expandedNotes, setExpandedNotes] = useState<Record<string, { id: string; content: string; created_at: string }[]>>({});

  const toggleNotes = useCallback(async (issueId: string) => {
    if (expandedNotes[issueId]) {
      // Collapse: remove note nodes
      setExpandedNotes(prev => { const next = { ...prev }; delete next[issueId]; return next; });
      setRfNodes(prev => prev.filter(n => !n.id.startsWith(`note-${issueId}-`)));
      setRfEdges(prev => prev.filter(e => !e.id.startsWith(`note-edge-${issueId}-`)));
    } else {
      // Expand: fetch notes and add as child nodes
      try {
        const res = await authFetch(`/api/issues/${issueId}/notes`);
        if (!res.ok) return;
        const data = await res.json();
        const notes = data.notes || [];
        if (notes.length === 0) return;

        setExpandedNotes(prev => ({ ...prev, [issueId]: notes }));

        // Find parent node position
        const parentNode = rfNodes.find(n => n.id === issueId);
        if (!parentNode) return;
        const baseX = parentNode.position.x + 260;
        const baseY = parentNode.position.y - ((notes.length - 1) * 35);

        const newNodes = notes.map((note: any, i: number) => ({
          id: `note-${issueId}-${note.id}`,
          type: 'default',
          position: { x: baseX, y: baseY + i * 70 },
          data: { label: `📝 ${(note.content || '').slice(0, 30)}${(note.content || '').length > 30 ? '...' : ''}` },
          style: {
            background: '#FEF9C3',
            border: '1px solid #FDE68A',
            borderRadius: 8,
            padding: '6px 10px',
            fontSize: 11,
            maxWidth: 180,
            cursor: 'default',
          },
        }));

        const newEdges = notes.map((note: any) => ({
          id: `note-edge-${issueId}-${note.id}`,
          source: issueId,
          target: `note-${issueId}-${note.id}`,
          type: 'default',
          animated: false,
          style: { stroke: '#FDE68A', strokeDasharray: '4 4' },
        }));

        setRfNodes(prev => [...prev, ...newNodes]);
        setRfEdges(prev => [...prev, ...newEdges]);
      } catch (e) {
        console.error('Failed to fetch notes:', e);
      }
    }
  }, [expandedNotes, rfNodes, setRfNodes, setRfEdges]);

  // --- Undo history ---
  type UndoAction =
    | { type: 'add_issue'; issueId: string }
    | { type: 'add_edge'; edgeId: string }
    | { type: 'delete_edge'; edge: { from_id: string; to_id: string } }
    | { type: 'patch_issue'; issueId: string; prevValues: Record<string, unknown> };
  const undoStackRef = useRef<UndoAction[]>([]);

  const pushUndo = useCallback((action: UndoAction) => {
    undoStackRef.current = [...undoStackRef.current.slice(-29), action];
  }, []);

  const handleUndo = useCallback(async () => {
    const action = undoStackRef.current.pop();
    if (!action) return;
    try {
      if (action.type === 'add_issue') {
        await authFetch(`/api/issues/${action.issueId}`, { method: 'DELETE' });
      } else if (action.type === 'add_edge') {
        await authFetch(`/api/issues/edges/${action.edgeId}`, { method: 'DELETE' });
      } else if (action.type === 'delete_edge') {
        await authFetch('/api/issues/edges/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ from_id: action.edge.from_id, to_id: action.edge.to_id, confirmed: true }),
        });
      } else if (action.type === 'patch_issue') {
        await authFetch(`/api/issues/${action.issueId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(action.prevValues),
        });
      }
      onRefresh();
    } catch (e) {
      console.error('undo failed', e);
    }
  }, [onRefresh]);

  // Keyboard shortcut ref (filled after handleFabClick is defined)
  const fabClickRef = useRef<() => void>(() => {});

  // --- Gap analysis ---
  const [gapEdges, setGapEdges] = useState<Edge[]>([]);
  const [gapLoading, setGapLoading] = useState(false);
  const [gapStats, setGapStats] = useState<{ nodes: number; edges: number; components: number } | null>(null);

  const runGapAnalysis = useCallback(async () => {
    if (!projectName || gapLoading) return;
    setGapLoading(true);
    try {
      const res = await authFetch(`/api/issues/graph-analysis?project_name=${encodeURIComponent(projectName)}`);
      const data = await res.json();
      setGapStats(data.stats || null);
      // ギャップ候補を点線エッジとして追加
      const newEdges: Edge[] = (data.gaps || []).flatMap((gap: any, gi: number) => {
        if (!gap.cluster_a?.[0] || !gap.cluster_b?.[0]) return [];
        return [{
          id: `gap-${gi}`,
          source: gap.cluster_a[0],
          target: gap.cluster_b[0],
          type: 'default',
          animated: true,
          style: { stroke: '#F59E0B', strokeDasharray: '6 4', strokeWidth: 2 },
          label: gap.suggestion?.slice(0, 30) || 'ギャップ候補',
          labelStyle: { fontSize: 9, fill: '#92400E' },
          labelBgStyle: { fill: '#FEF3C7', fillOpacity: 0.9 },
        }];
      });
      setGapEdges(newEdges);
    } catch {
      // silent
    } finally {
      setGapLoading(false);
    }
  }, [projectName, gapLoading]);

  const clearGaps = useCallback(() => {
    setGapEdges([]);
    setGapStats(null);
  }, []);

  // --- Context menu ---
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number;
    issueId?: string;
    edgeId?: string;
  } | null>(null);

  // --- Delete confirmation state ---
  const [deleteEdgeId, setDeleteEdgeId] = useState<string | null>(null);

  // --- Inline input state (Phase 2) ---
  const [inlineInput, setInlineInput] = useState<{
    x: number;       // flow coordinate (for saving position)
    y: number;
    screenX: number; // screen coordinate (for overlay position)
    screenY: number;
    sourceNodeId?: string;
  } | null>(null);
  const [inlineText, setInlineText] = useState('');
  const [inlineSubmitting, setInlineSubmitting] = useState(false);
  const inlineRef = useRef<HTMLInputElement>(null);

  // fitViewTrigger
  useEffect(() => {
    if (fitViewTrigger !== undefined && fitViewTrigger > 0) {
      fitView({ padding: 0.2 });
    }
  }, [fitViewTrigger, fitView]);

  // Focus inline input when shown
  useEffect(() => {
    if (inlineInput) {
      setTimeout(() => inlineRef.current?.focus(), 50);
    }
  }, [inlineInput]);

  // 折りたたまれた子ノードのセットを計算
  const collapsedChildIds = useMemo(() => {
    const collapsed = new Set<string>();
    const collapsedIssueIds = new Set(
      issues.filter((iss) => iss.is_collapsed === 1).map((iss) => iss.id)
    );
    // 隣接リスト: from_id → to_id[]
    const childrenOf = new Map<string, string[]>();
    edges.forEach((e) => {
      if (!childrenOf.has(e.from_id)) childrenOf.set(e.from_id, []);
      childrenOf.get(e.from_id)!.push(e.to_id);
    });
    // 再帰的に全子孫を非表示にする
    function hideDescendants(nodeId: string) {
      const children = childrenOf.get(nodeId) || [];
      for (const childId of children) {
        if (!collapsed.has(childId)) {
          collapsed.add(childId);
          hideDescendants(childId);
        }
      }
    }
    collapsedIssueIds.forEach((id) => hideDescendants(id));
    return collapsed;
  }, [issues, edges]);

  const visibleIssues = useMemo(
    () => issues.filter((iss) => !collapsedChildIds.has(iss.id)),
    [issues, collapsedChildIds]
  );

  const hiddenChildCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    const childrenOf = new Map<string, string[]>();
    edges.forEach((e) => {
      if (!childrenOf.has(e.from_id)) childrenOf.set(e.from_id, []);
      childrenOf.get(e.from_id)!.push(e.to_id);
    });
    function countDescendants(nodeId: string, visited: Set<string>): number {
      let count = 0;
      for (const childId of (childrenOf.get(nodeId) || [])) {
        if (!visited.has(childId)) {
          visited.add(childId);
          count += 1 + countDescendants(childId, visited);
        }
      }
      return count;
    }
    issues
      .filter((iss) => iss.is_collapsed === 1)
      .forEach((iss) => {
        const total = countDescendants(iss.id, new Set([iss.id]));
        if (total > 0) counts[iss.id] = total;
      });
    return counts;
  }, [issues, edges]);

  const issueIdsWithChildren = useMemo(() => {
    return new Set(edges.map((e) => e.from_id));
  }, [edges]);

  // --- Stable callbacks for IssueNode (fixes React.memo P2) ---
  const stableOnNodeClick = useCallback(
    (issue: Issue) => onNodeClick(issue),
    [onNodeClick]
  );

  const handleCollapseToggle = useCallback(
    async (issue: Issue) => {
      try {
        const res = await authFetch(`/api/issues/${issue.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_collapsed: issue.is_collapsed === 1 ? 0 : 1 }),
        });
        if (res.ok) onRefresh();
      } catch (e) {
        console.error('collapse toggle failed', e);
      }
    },
    [onRefresh]
  );

  const handleTitleChange = useCallback(
    async (issueId: string, newTitle: string) => {
      const prev = issues.find(i => i.id === issueId);
      try {
        const res = await authFetch(`/api/issues/${issueId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: newTitle }),
        });
        if (res.ok) {
          if (prev) pushUndo({ type: 'patch_issue', issueId, prevValues: { title: prev.title } });
          onRefresh();
        }
      } catch (e) {
        console.error('title change failed', e);
      }
    },
    [issues, onRefresh, pushUndo]
  );

  // --- Edge delete with confirmation ---
  const handleDeleteEdgeRequest = useCallback(
    (edgeId: string) => setDeleteEdgeId(edgeId),
    []
  );

  const handleDeleteEdgeConfirm = useCallback(async () => {
    if (!deleteEdgeId) return;
    const edge = edges.find(e => e.id === deleteEdgeId);
    try {
      await authFetch(`/api/issues/edges/${deleteEdgeId}`, { method: 'DELETE' });
      if (edge) pushUndo({ type: 'delete_edge', edge: { from_id: edge.from_id, to_id: edge.to_id } });
      onRefresh();
    } catch (e) {
      console.error('edge delete failed', e);
    } finally {
      setDeleteEdgeId(null);
    }
  }, [deleteEdgeId, edges, onRefresh, pushUndo]);

  // --- Build nodes & edges ---
  useEffect(() => {
    const visibleIds = new Set(visibleIssues.map((iss) => iss.id));

    const nodes: Node[] = visibleIssues.map((iss) => {
      const isDimmed =
        (priorityFilter === 'critical' && iss.priority !== 'critical') ||
        (priorityFilter === 'normal_up' && iss.priority === 'minor');

      if (isDimmed && iss.priority === 'minor') {
        return {
          id: iss.id,
          type: 'default',
          position: { x: iss.pos_x, y: iss.pos_y },
          data: { label: '' },
          style: {
            width: 12, height: 12, borderRadius: '50%',
            background: '#B4B2A9', border: 'none', padding: 0,
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
          hasChildren: issueIdsWithChildren.has(iss.id),
          attachmentCount: (iss as any).attachment_count ?? 0,
          onClick: stableOnNodeClick,
          onCollapseToggle: handleCollapseToggle,
          onTitleChange: handleTitleChange,
          onToggleNotes: toggleNotes,
          notesExpanded: !!expandedNotes[iss.id],
        },
      };
    });

    const visibleEdges: Edge[] = edges
      .filter((e) => visibleIds.has(e.from_id) && visibleIds.has(e.to_id))
      .map((e) => ({
        id: e.id,
        source: e.from_id,
        target: e.to_id,
        type: 'deletable',
        animated: e.confirmed === 0,
        style: e.confirmed === 1
          ? { stroke: '#E24B4A', strokeWidth: 2 }
          : { stroke: '#B4B2A9', strokeWidth: 1.5, strokeDasharray: '5 4' },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: e.confirmed === 1 ? '#E24B4A' : '#B4B2A9',
        },
        data: { onDeleteEdge: handleDeleteEdgeRequest },
      }));

    // --- Smart layout (Phase 2 fix) ---
    const allAtOrigin = nodes.length > 0 && nodes.every(
      (n) => n.position.x === 0 && n.position.y === 0
    );

    let finalNodes: Node[];
    if (allAtOrigin) {
      // All nodes at origin → full dagre layout
      finalNodes = buildDagreLayout(nodes, visibleEdges);
    } else {
      // Place individual new nodes (at 0,0) to the right of existing nodes
      const positioned = nodes.filter((n) => n.position.x !== 0 || n.position.y !== 0);
      let offsetIdx = 0;
      finalNodes = nodes.map((n) => {
        if (n.position.x === 0 && n.position.y === 0 && positioned.length > 0) {
          const base = computeNewNodePosition(positioned);
          const pos = { x: base.x, y: base.y + offsetIdx * (NODE_H + 30) };
          offsetIdx++;
          // Persist the computed position
          authFetch(`/api/issues/${n.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pos_x: pos.x, pos_y: pos.y }),
          }).catch(() => {});
          return { ...n, position: pos };
        }
        return n;
      });
    }

    setRfNodes(finalNodes);
    setRfEdges([...visibleEdges, ...gapEdges]);

    if (finalNodes.length > 0 && !initialFitDone.current) {
      initialFitDone.current = true;
      setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50);
    }
  }, [issues, edges, priorityFilter, visibleIssues, hiddenChildCounts, issueIdsWithChildren, stableOnNodeClick, handleCollapseToggle, handleTitleChange, toggleNotes, expandedNotes, handleDeleteEdgeRequest, fitView, gapEdges]);

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

  const handleConnect = useCallback(
    async (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      const duplicate = edges.some(
        (e) => e.from_id === connection.source && e.to_id === connection.target
      );
      if (duplicate) return;

      // 楽観的更新: API応答を待たずに即座にUIにエッジを表示
      const tempId = `temp-${Date.now()}`;
      setRfEdges((prev) => [
        ...prev,
        {
          id: tempId,
          source: connection.source!,
          target: connection.target!,
          type: 'deletable',
          animated: true, // 仮エッジはアニメーション表示
          markerEnd: { type: MarkerType.ArrowClosed, color: '#999' },
        },
      ]);

      // バックグラウンドでAPI呼び出し → 成功したら正式なエッジに差し替え
      try {
        const res = await authFetch('/api/issues/edges/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_id: connection.source,
            to_id: connection.target,
            confirmed: true,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.edge_id) pushUndo({ type: 'add_edge', edgeId: data.edge_id });
        }
        onRefresh();
      } catch (e) {
        // 失敗時は仮エッジを除去
        setRfEdges((prev) => prev.filter((ed) => ed.id !== tempId));
        console.error('connect failed', e);
      }
    },
    [edges, onRefresh, pushUndo, setRfEdges]
  );

  // --- Phase 2: Double-click to add node ---
  const handlePaneDoubleClick = useCallback(
    (event: React.MouseEvent) => {
      if (!projectName) return;
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      setInlineInput({ x: position.x, y: position.y, screenX: event.clientX, screenY: event.clientY });
      setInlineText('');
    },
    [projectName, screenToFlowPosition]
  );

  // --- Phase 2: FAB button to add node ---
  const handleFabClick = useCallback(() => {
    if (!projectName) return;
    const pos = computeNewNodePosition(rfNodes);
    const screen = flowToScreenPosition({ x: pos.x, y: pos.y });
    setInlineInput({ x: pos.x, y: pos.y, screenX: screen.x, screenY: screen.y });
    setInlineText('');
  }, [projectName, rfNodes, flowToScreenPosition]);

  // Update ref for keyboard shortcut
  useEffect(() => { fabClickRef.current = handleFabClick; }, [handleFabClick]);

  // Delete selected elements
  const deleteSelected = useCallback(async () => {
    const selNodes = rfNodes.filter(n => n.selected);
    const selEdges = rfEdges.filter(ed => ed.selected);
    let changed = false;

    for (const n of selNodes) {
      try {
        await authFetch(`/api/issues/${n.id}`, { method: 'DELETE' });
        pushUndo({ type: 'add_issue', issueId: n.id });
        changed = true;
      } catch {}
    }

    for (const ed of selEdges) {
      const edge = edges.find(e => e.id === ed.id);
      try {
        await authFetch(`/api/issues/edges/${ed.id}`, { method: 'DELETE' });
        if (edge) pushUndo({ type: 'delete_edge', edge: { from_id: edge.from_id, to_id: edge.to_id } });
        changed = true;
      } catch {}
    }

    if (changed) onRefresh();
    return selNodes.length + selEdges.length;
  }, [rfNodes, rfEdges, edges, onRefresh, pushUndo]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault(); handleUndo(); return;
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault(); deleteSelected(); return;
      }
      if (e.key === 'n' && !e.metaKey && !e.ctrlKey) { e.preventDefault(); fabClickRef.current(); return; }
      if (e.key === 'f' && !e.metaKey && !e.ctrlKey) { e.preventDefault(); fitView({ padding: 0.2 }); return; }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleUndo, deleteSelected, fitView]);

  // --- Phase 2: Submit inline node ---
  const handleInlineSubmit = useCallback(async () => {
    if (!inlineText.trim() || !projectName || inlineSubmitting) return;
    const text = inlineText.trim();
    const pos = inlineInput ? { x: inlineInput.x, y: inlineInput.y } : { x: 0, y: 0 };
    const sourceNodeId = inlineInput?.sourceNodeId;

    // 楽観的更新: 仮ノードを即座に表示
    const tempId = `temp-${Date.now()}`;
    setRfNodes((prev) => [
      ...prev,
      {
        id: tempId,
        type: 'issueNode',
        position: pos,
        data: {
          issue: {
            id: tempId, project_name: projectName, title: text, raw_input: text,
            category: '工程', priority: 'normal', status: '発生中',
            description: null, cause: null, impact: null, action_next: null,
            is_collapsed: 0, pos_x: pos.x, pos_y: pos.y, template_id: null,
            created_at: '', updated_at: '', assignee: null, deadline: null, context_memo: null,
            is_task: 0, completed_at: null, due_time: null, section_name: null,
          } as Issue,
        },
      },
    ]);

    // 仮エッジ（接続元がある場合）
    if (sourceNodeId) {
      setRfEdges((prev) => [
        ...prev,
        {
          id: `temp-edge-${Date.now()}`,
          source: sourceNodeId,
          target: tempId,
          type: 'deletable',
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed, color: '#999' },
        },
      ]);
    }

    setInlineSubmitting(true);
    setInlineInput(null);
    setInlineText('');

    try {
      const res = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_input: text,
          project_name: projectName,
          skip_ai: true,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: CaptureResponse = await res.json();

      // エッジ作成 + 位置保存を並列実行
      const promises: Promise<any>[] = [];
      if (sourceNodeId && data.issue) {
        promises.push(authFetch('/api/issues/edges/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ from_id: sourceNodeId, to_id: data.issue.id, confirmed: true }),
        }));
      }
      if (data.issue) {
        promises.push(authFetch(`/api/issues/${data.issue.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pos_x: pos.x, pos_y: pos.y }),
        }));
      }
      await Promise.all(promises);

      if (data.issue) pushUndo({ type: 'add_issue', issueId: data.issue.id });
      onIssueAdded?.(data);
      onRefresh();
    } catch (e) {
      // 失敗時は仮ノード・仮エッジを除去
      setRfNodes((prev) => prev.filter((n) => n.id !== tempId));
      setRfEdges((prev) => prev.filter((ed) => !ed.id.startsWith('temp-')));
      console.error('inline add failed', e);
    } finally {
      setInlineSubmitting(false);
    }
  }, [inlineText, projectName, inlineSubmitting, inlineInput, onIssueAdded, onRefresh, pushUndo, setRfNodes, setRfEdges]);

  // --- Phase 2: Connect end to empty space → inline input ---
  const handleConnectEnd = useCallback(
    (event: MouseEvent | TouchEvent) => {
      if (!projectName) return;
      // Only handle mouse events for now
      if (!(event instanceof MouseEvent)) return;
      const target = event.target as HTMLElement;
      // Check if dropped on empty pane (not on a node)
      if (target.closest('.react-flow__node')) return;

      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });

      // Get the source node from the connecting edge
      const connectingEdge = document.querySelector('.react-flow__connection');
      const sourceHandle = document.querySelector('.connecting');
      const sourceNode = sourceHandle?.closest('.react-flow__node');
      const sourceNodeId = sourceNode?.getAttribute('data-id') ?? undefined;

      setInlineInput({ x: position.x, y: position.y, screenX: event.clientX, screenY: event.clientY, sourceNodeId });
      setInlineText('');
    },
    [projectName, screenToFlowPosition]
  );

  // Right-click context menu
  const handleContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    const target = event.target as HTMLElement;
    const nodeEl = target.closest('.react-flow__node');
    const edgeEl = target.closest('.react-flow__edge');
    if (nodeEl) {
      const nodeId = nodeEl.getAttribute('data-id') || '';
      setContextMenu({ x: event.clientX, y: event.clientY, issueId: nodeId });
    } else if (edgeEl) {
      // edge id is in the element's data attributes
      const edgeId = edgeEl.getAttribute('data-testid')?.replace('rf__edge-', '') || '';
      setContextMenu({ x: event.clientX, y: event.clientY, edgeId });
    } else {
      // Pane right-click → add node
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      setContextMenu({ x: event.clientX, y: event.clientY });
    }
  }, [screenToFlowPosition]);

  return (
    <div
      style={{ width: '100%', height: '100%', position: 'relative' }}
      onContextMenu={handleContextMenu}
      onClick={() => setContextMenu(null)}
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={handleNodeDragStop}
        onConnect={handleConnect}
        onConnectEnd={handleConnectEnd}
        onDoubleClick={handlePaneDoubleClick}
        elementsSelectable
        selectNodesOnDrag={false}
        selectionOnDrag
        selectionMode={'partial' as any}
        edgesFocusable
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={3}
        zoomOnPinch
        panOnScroll={false}
        deleteKeyCode={null}
      >
        <Background gap={16} color="#e5e7eb" />
        {/* Gap analysis button */}
        {projectName && (
          <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 10, display: 'flex', gap: 4 }}>
            {gapEdges.length > 0 && (
              <button
                onClick={clearGaps}
                style={{
                  fontSize: 11, padding: '4px 10px', borderRadius: 6,
                  background: '#FEF3C7', border: '1px solid #F59E0B', color: '#92400E', cursor: 'pointer',
                }}
              >
                ギャップ非表示
              </button>
            )}
            <button
              onClick={runGapAnalysis}
              disabled={gapLoading}
              style={{
                fontSize: 11, padding: '4px 10px', borderRadius: 6,
                background: gapLoading ? '#F3F4F6' : '#EFF6FF', border: '1px solid #93C5FD',
                color: '#1D4ED8', cursor: gapLoading ? 'wait' : 'pointer',
              }}
            >
              {gapLoading ? '分析中...' : '🔍 ギャップ検出'}
            </button>
            {gapStats && (
              <span style={{ fontSize: 10, color: '#6B7280', lineHeight: '28px' }}>
                {gapStats.components}グループ / {gapStats.nodes}ノード
              </span>
            )}
          </div>
        )}
        <div className="hidden md:block">
          <Controls />
        </div>
        <div className="hidden md:block">
          <MiniMap nodeColor={(n) => {
            const iss = issues.find((i) => i.id === n.id);
            if (!iss) return '#ccc';
            return iss.priority === 'critical' ? '#F7C1C1' : iss.priority === 'minor' ? '#F1EFE8' : '#B5D4F4';
          }} />
        </div>
      </ReactFlow>

      {/* Inline input overlay — fixed position using screen coordinates */}
      {inlineInput && (
        <div
          className="fixed z-50"
          style={{
            left: inlineInput.screenX,
            top: inlineInput.screenY,
            transform: 'translate(-50%, -50%)',
          }}
        >
          <div className="bg-white border-2 border-blue-500 rounded-2xl shadow-2xl px-4 py-3 flex flex-col gap-2 min-w-[280px] max-w-[90vw]">
            {inlineInput.sourceNodeId && (
              <span className="text-[10px] text-blue-500 font-medium">因果関係の先にノードを追加</span>
            )}
            <div className="flex items-center gap-2">
              <input
                ref={inlineRef}
                value={inlineText}
                onChange={(e) => setInlineText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    handleInlineSubmit();
                  }
                  if (e.key === 'Escape') {
                    setInlineInput(null);
                    setInlineText('');
                  }
                }}
                placeholder="課題を入力してEnter"
                disabled={inlineSubmitting}
                className="flex-1 text-sm border-none outline-none bg-transparent text-gray-800 placeholder-gray-400"
                autoComplete="off"
              />
              {inlineSubmitting ? (
                <span className="text-xs text-blue-500 animate-pulse whitespace-nowrap">追加中...</span>
              ) : (
                <button
                  onClick={handleInlineSubmit}
                  disabled={!inlineText.trim()}
                  className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-30 transition-all whitespace-nowrap"
                >
                  追加
                </button>
              )}
            </div>
            <button
              onClick={() => { setInlineInput(null); setInlineText(''); }}
              className="text-[10px] text-gray-400 hover:text-gray-600 self-end"
            >
              キャンセル
            </button>
          </div>
        </div>
      )}

      {/* FAB button — larger and more visible */}
      {projectName && !inlineInput && (
        <button
          onClick={handleFabClick}
          title="課題を追加"
          className="absolute bottom-20 md:bottom-4 right-4 z-10 w-14 h-14 rounded-full bg-blue-600 text-white shadow-lg flex items-center justify-center hover:bg-blue-700 active:scale-95 transition-all hover:shadow-xl"
        >
          <Plus size={24} />
        </button>
      )}

      {/* Context menu */}
      {contextMenu && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setContextMenu(null)} />
          <div
            className="fixed z-50 bg-white border border-gray-200 rounded-xl shadow-xl py-1 min-w-[160px]"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            {contextMenu.issueId ? (
              <>
                <button
                  onClick={() => {
                    const iss = issues.find(i => i.id === contextMenu.issueId);
                    if (iss) onNodeClick(iss);
                    setContextMenu(null);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  詳細を開く
                </button>
                <button
                  onClick={async () => {
                    await authFetch(`/api/issues/${contextMenu.issueId}`, { method: 'DELETE' });
                    pushUndo({ type: 'add_issue', issueId: contextMenu.issueId! });
                    onRefresh();
                    setContextMenu(null);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  削除
                </button>
              </>
            ) : contextMenu.edgeId ? (
              <button
                onClick={() => {
                  setDeleteEdgeId(contextMenu.edgeId!);
                  setContextMenu(null);
                }}
                className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                エッジを削除
              </button>
            ) : (
              <>
                <button
                  onClick={() => {
                    handleFabClick();
                    setContextMenu(null);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  課題を追加 <span className="text-gray-400 ml-2 text-xs">N</span>
                </button>
                <button
                  onClick={() => {
                    fitView({ padding: 0.2 });
                    setContextMenu(null);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  全体表示 <span className="text-gray-400 ml-2 text-xs">F</span>
                </button>
                {undoStackRef.current.length > 0 && (
                  <button
                    onClick={() => {
                      handleUndo();
                      setContextMenu(null);
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    元に戻す <span className="text-gray-400 ml-2 text-xs">⌘Z</span>
                  </button>
                )}
              </>
            )}
          </div>
        </>
      )}

      {/* Keyboard shortcuts hint (desktop only) */}
      <div className="absolute top-3 right-3 z-10 hidden md:flex gap-1 text-[10px] text-gray-400 select-none">
        <span className="bg-gray-100 px-1.5 py-0.5 rounded">N 追加</span>
        <span className="bg-gray-100 px-1.5 py-0.5 rounded">F 全体表示</span>
        <span className="bg-gray-100 px-1.5 py-0.5 rounded">⌘Z 戻す</span>
        <span className="bg-gray-100 px-1.5 py-0.5 rounded">⌫ 選択削除</span>
        <span className="bg-gray-100 px-1.5 py-0.5 rounded">ドラッグ 範囲選択</span>
      </div>

      {/* Phase 1: Delete edge confirmation dialog */}
      <ConfirmDialog
        open={deleteEdgeId !== null}
        title="エッジを削除"
        message="この因果関係を削除しますか？"
        confirmLabel="削除"
        danger
        onConfirm={handleDeleteEdgeConfirm}
        onCancel={() => setDeleteEdgeId(null)}
      />
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
