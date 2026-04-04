'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import Link from 'next/link';
import { ArrowLeft, Loader2, Radio } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface MeetingNode {
  id: number;
  title: string;
  created_at: string;
  series_name: string | null;
  tags: string[];
}

interface MeetingLink {
  source_id: number;
  target_id: number;
  mention_text: string;
}

const NODE_WIDTH = 220;
const NODE_HEIGHT = 80;

function buildLayout(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: 120 });

  nodes.forEach(n => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach(e => g.setEdge(e.source, e.target));
  dagre.layout(g);

  const laid = nodes.map(n => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
  return { nodes: laid, edges };
}

function MeetingNodeComponent({ data }: { data: any }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm hover:shadow-md transition-shadow w-[220px]">
      <p className="text-sm font-medium text-gray-800 truncate">{data.title}</p>
      <p className="text-xs text-gray-400 mt-0.5">{data.date}</p>
      {data.series && (
        <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-600">
          {data.series}
        </span>
      )}
      {data.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {data.tags.slice(0, 3).map((t: string) => (
            <span key={t} className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-500">{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}

const nodeTypes = { meeting: MeetingNodeComponent };

export default function MeetingGraphPage() {
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    (async () => {
      try {
        // 全会議 + エンティティリンクを取得
        const meetingsRes = await authFetch('/api/meetings');
        const meetings = meetingsRes.ok ? await meetingsRes.json() : [];

        // 各会議のタグとリンクを取得（並列、最大20件）
        const meetingData: MeetingNode[] = [];
        const allLinks: MeetingLink[] = [];

        const batch = meetings.slice(0, 30);
        await Promise.all(batch.map(async (m: any) => {
          meetingData.push({
            id: m.id,
            title: m.title,
            created_at: m.created_at,
            series_name: m.series_name,
            tags: [],
          });

          try {
            const [tagsRes, linksRes] = await Promise.all([
              authFetch(`/api/meetings/${m.id}/tags`),
              authFetch(`/api/meetings/${m.id}/entity-links`),
            ]);
            if (tagsRes.ok) {
              const tags = await tagsRes.json();
              const node = meetingData.find(n => n.id === m.id);
              if (node) node.tags = tags.map((t: any) => t.tag_name);
            }
            if (linksRes.ok) {
              const links = await linksRes.json();
              links
                .filter((l: any) => l.entity_type === 'meeting')
                .forEach((l: any) => {
                  allLinks.push({
                    source_id: m.id,
                    target_id: parseInt(l.entity_id),
                    mention_text: l.mention_text,
                  });
                });
            }
          } catch {}
        }));

        // ReactFlow ノード・エッジ構築
        const meetingIds = new Set(meetingData.map(m => m.id));
        const rfNodes: Node[] = meetingData.map(m => ({
          id: String(m.id),
          type: 'meeting',
          position: { x: 0, y: 0 },
          data: {
            title: m.title,
            date: (m.created_at || '').slice(0, 10),
            series: m.series_name,
            tags: m.tags,
          },
        }));

        const rfEdges: Edge[] = allLinks
          .filter(l => meetingIds.has(l.source_id) && meetingIds.has(l.target_id))
          .map((l, i) => ({
            id: `e-${l.source_id}-${l.target_id}-${i}`,
            source: String(l.source_id),
            target: String(l.target_id),
            label: l.mention_text?.slice(0, 20),
            style: { stroke: '#6366f1', strokeWidth: 1.5 },
            animated: true,
          }));

        const { nodes: laidNodes, edges: laidEdges } = buildLayout(rfNodes, rfEdges);
        setNodes(laidNodes);
        setEdges(laidEdges);
      } catch (e) {
        console.error('Failed to load graph:', e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-4 md:px-8 py-4 flex-shrink-0">
        <div className="max-w-7xl mx-auto flex items-center gap-3">
          <Link
            href="/meetings"
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <Radio className="w-5 h-5 text-indigo-500" />
          <h1 className="text-lg font-bold text-gray-900">会議リンクグラフ</h1>
          <span className="text-sm text-gray-400 ml-2">
            {nodes.length}件の会議 / {edges.length}件のリンク
          </span>
        </div>
      </header>

      <div className="flex-1" style={{ height: 'calc(100vh - 65px)' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.3}
          maxZoom={2}
        >
          <Background gap={20} size={1} />
          <Controls />
          <MiniMap
            nodeColor="#6366f1"
            nodeStrokeWidth={0}
            style={{ background: '#f9fafb' }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
