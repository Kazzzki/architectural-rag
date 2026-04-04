'use client';

import { useMemo, useCallback } from 'react';
import ReactFlow, {
  Background, Controls, MiniMap, Panel,
  useNodesState, useEdgesState,
  type Node, type Edge, MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';

interface Task {
  id: number; title: string; status: string; priority: string;
  category_name?: string | null; category_color?: string | null;
}

const PCOL: Record<string, string> = { high: '#EF4444', medium: '#3B82F6', low: '#9CA3AF' };

function buildLayout(tasks: Task[]): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []; const edges: Edge[] = [];
  const active = tasks.filter(t => t.status !== 'done');
  const cats = new Map<string, Task[]>();
  for (const t of active) { const c = t.category_name || '未分類'; (cats.get(c) || (() => { const a: Task[] = []; cats.set(c, a); return a; })()).push(t); }

  nodes.push({ id: 'root', type: 'default', position: { x: 0, y: 0 }, data: { label: `タスク (${active.length})` },
    style: { background: '#4F46E5', color: '#fff', border: 'none', borderRadius: '12px', padding: '8px 16px', fontWeight: 'bold', fontSize: '14px' } });

  const keys = [...cats.keys()]; const step = (2 * Math.PI) / Math.max(keys.length, 1);
  keys.forEach((name, ci) => {
    const a = step * ci - Math.PI / 2, cx = Math.cos(a) * 250, cy = Math.sin(a) * 250, cid = `c-${ci}`;
    const ct = cats.get(name)!, col = ct[0]?.category_color || '#818CF8';
    nodes.push({ id: cid, type: 'default', position: { x: cx, y: cy }, data: { label: `${name} (${ct.length})` },
      style: { background: col + '15', border: `2px solid ${col}`, borderRadius: '10px', padding: '6px 14px', fontWeight: '600', fontSize: '12px', color: col } });
    edges.push({ id: `r-${cid}`, source: 'root', target: cid, type: 'smoothstep', style: { stroke: '#C7D2FE', strokeWidth: 2 } });
    const ts = Math.PI / Math.max(ct.length + 1, 2);
    ct.forEach((t, ti) => {
      const ta = a - Math.PI / 2 + ts * (ti + 1), tx = cx + Math.cos(ta) * 160, ty = cy + Math.sin(ta) * 160, pc = PCOL[t.priority] || PCOL.medium;
      nodes.push({ id: String(t.id), type: 'default', position: { x: tx, y: ty }, data: { label: t.title },
        style: { background: '#fff', border: `2px solid ${pc}`, borderRadius: '8px', padding: '6px 10px', fontSize: '11px', color: '#374151', maxWidth: '180px', borderLeftWidth: '4px', borderLeftColor: pc } });
      edges.push({ id: `${cid}-${t.id}`, source: cid, target: String(t.id), type: 'smoothstep', style: { stroke: '#E5E7EB', strokeWidth: 1.5 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#E5E7EB' } });
    });
  });
  return { nodes, edges };
}

export default function TaskMindMap({ tasks, onSelect }: { tasks: Task[]; onSelect: (id: number) => void }) {
  const { nodes: ini, edges: inie } = useMemo(() => buildLayout(tasks), [tasks]);
  const [nodes, , onNC] = useNodesState(ini);
  const [edges, , onEC] = useEdgesState(inie);
  const onClick = useCallback((_: React.MouseEvent, n: Node) => { if (n.id !== 'root' && !n.id.startsWith('c-')) onSelect(Number(n.id)); }, [onSelect]);

  return (
    <div className="w-full h-full" style={{ minHeight: 500 }}>
      <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNC} onEdgesChange={onEC} onNodeClick={onClick} fitView minZoom={0.3} maxZoom={2} proOptions={{ hideAttribution: true }}>
        <Background color="#F3F4F6" gap={20} size={1} />
        <Controls className="!bg-white !border-gray-200 !rounded-lg !shadow-sm" />
        <MiniMap className="!bg-gray-50 !border-gray-200" nodeColor={n => n.id === 'root' ? '#4F46E5' : n.id.startsWith('c-') ? '#818CF8' : '#93C5FD'} />
        <Panel position="top-left" className="text-xs text-gray-400">ドラッグ/スクロールで操作</Panel>
      </ReactFlow>
    </div>
  );
}
