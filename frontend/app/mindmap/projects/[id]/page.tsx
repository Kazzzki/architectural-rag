'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ReactFlowProvider } from 'reactflow';
import MindmapCanvas from '../../../components/mindmap/MindmapCanvas';
import NodeDetailPanel from '../../../components/mindmap/NodeDetailPanel';
import GoalSearchBar from '../../../components/mindmap/GoalSearchBar';
import EditToolbar from '../../../components/mindmap/EditToolbar';
import AddNodeDialog from '../../../components/mindmap/AddNodeDialog';
import ContextMenu from '../../../components/mindmap/ContextMenu';
import { Building2, ArrowLeft, Filter, ChevronDown, Plus, Edit2, Trash2, CornerDownRight, Minimize2, Maximize2 } from 'lucide-react';
import Link from 'next/link';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ProcessNode {
    id: string;
    label: string;
    description: string;
    phase: string;
    category: string;
    checklist: string[];
    deliverables: string[];
    key_stakeholders: string[];
    position: { x: number; y: number };
    status: string;
    is_custom?: boolean;
}

interface EdgeData {
    id: string;
    source: string;
    target: string;
    type: string;
    reason: string;
}

interface ProjectData {
    id: string;
    name: string;
    description: string;
    template_id: string;
    created_at: string;
    updated_at: string;
    nodes: ProcessNode[];
    edges: EdgeData[];
}

const PHASES = ['基本計画', '基本設計', '実施設計', '施工準備', '施工'];
const CATEGORIES = ['構造', '意匠', '設備', '外装', '土木', '管理'];

const CATEGORY_COLORS: Record<string, string> = {
    '構造': '#ef4444',
    '意匠': '#3b82f6',
    '設備': '#22c55e',
    '外装': '#f59e0b',
    '土木': '#8b5cf6',
    '管理': '#6b7280',
};

export default function ProjectMapPage() {
    const params = useParams();
    const router = useRouter();
    const projectId = params.id as string;

    const [project, setProject] = useState<ProjectData | null>(null);
    const [loading, setLoading] = useState(true);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
    const [highlightedEdges, setHighlightedEdges] = useState<Set<string>>(new Set());
    const [collapsedNodeIds, setCollapsedNodeIds] = useState<Set<string>>(new Set());
    const [filterPhases, setFilterPhases] = useState<Set<string>>(new Set(PHASES));
    const [filterCategories, setFilterCategories] = useState<Set<string>>(new Set(CATEGORIES));
    const [isFilterOpen, setIsFilterOpen] = useState(false);
    const [isEditMode, setIsEditMode] = useState(false);
    const [showAddDialog, setShowAddDialog] = useState(false);
    const [undoCount, setUndoCount] = useState(0);
    const [nextActions, setNextActions] = useState<any[]>([]);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
    const [contextMenu, setContextMenu] = useState<{ x: number; y: number; type: 'node' | 'pane'; targetId?: string } | null>(null);
    const [selectedNodeIds, setSelectedNodeIds] = useState<Set<string>>(new Set());

    const activeNodes = project?.nodes || [];
    const activeEdges = project?.edges || [];

    // Load project data
    const loadProject = useCallback(async (isInitial = false) => {
        if (isInitial) setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/mindmap/projects/${projectId}`);
            if (!res.ok) throw new Error('Project not found');
            const data = await res.json();
            setProject(data);

            // Load next actions
            const actionsRes = await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/next-actions`);
            if (actionsRes.ok) {
                setNextActions(await actionsRes.json());
            }
        } catch (err) {
            console.error('Project load error:', err);
            router.push('/mindmap');
        } finally {
            if (isInitial) setLoading(false);
        }
    }, [projectId, router]);

    useEffect(() => {
        loadProject(true);
    }, [loadProject]);

    // Auto-save status display
    const showSaveStatus = useCallback(() => {
        setSaveStatus('saving');
        setTimeout(() => setSaveStatus('saved'), 500);
        setTimeout(() => setSaveStatus('idle'), 2500);
    }, []);

    // Goal search
    const handleGoalSearch = async (nodeId: string) => {
        if (!project) return;
        try {
            const res = await fetch(`${API_BASE}/api/mindmap/tree/${project.template_id}/${nodeId}`);
            const data = await res.json();
            setHighlightedNodes(new Set(data.path_order));
            const edgeIds = new Set<string>();
            activeEdges.forEach(e => {
                if (data.path_order.includes(e.source) && data.path_order.includes(e.target)) {
                    edgeIds.add(e.id);
                }
            });
            setHighlightedEdges(edgeIds);
        } catch (err) {
            console.error('Search error:', err);
        }
    };

    const clearHighlight = () => {
        setHighlightedNodes(new Set());
        setHighlightedEdges(new Set());
    };

    // Node operations
    const handleStatusChange = async (nodeId: string, newStatus: string) => {
        try {
            await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus }),
            });
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Status update error:', err);
        }
    };

    // Batch status change for multiple selected nodes
    const handleBatchStatusChange = async (newStatus: string) => {
        const ids = Array.from(selectedNodeIds);
        if (ids.length === 0) return;
        try {
            await Promise.all(ids.map(nodeId =>
                fetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus }),
                })
            ));
            setUndoCount(prev => prev + ids.length);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Batch status error:', err);
        }
    };

    // Selection change from canvas
    const handleSelectionChange = useCallback((nodeIds: string[]) => {
        setSelectedNodeIds(new Set(nodeIds));
        if (nodeIds.length === 1) {
            setSelectedNodeId(nodeIds[0]);
        }
    }, []);

    const handleNodeDragStop = async (nodeId: string, x: number, y: number) => {
        try {
            await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pos_x: x, pos_y: y }),
            });
            showSaveStatus();
        } catch (err) {
            console.error('Drag error:', err);
        }
    };

    const handleNodeLabelChange = async (nodeId: string, newLabel: string) => {
        try {
            await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label: newLabel }),
            });
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Label update error:', err);
        }
    };

    const handleNodeCollapse = (nodeId: string) => {
        setCollapsedNodeIds(prev => {
            const next = new Set(prev);
            if (next.has(nodeId)) {
                next.delete(nodeId);
            } else {
                next.add(nodeId);
            }
            return next;
        });
    };

    // Inline drag-to-create: add node at position with optional source edge
    const handleAddNodeAt = async (label: string, x: number, y: number, sourceNodeId?: string) => {
        try {
            // Find source node's category to inherit
            const sourceNode = sourceNodeId ? activeNodes.find(n => n.id === sourceNodeId) : null;

            const res = await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    label,
                    description: '',
                    phase: sourceNode?.phase || '基本計画',
                    category: sourceNode?.category || '管理',
                    checklist: [],
                    pos_x: x,
                    pos_y: y,
                }),
            });

            if (res.ok && sourceNodeId) {
                const newNode = await res.json();
                const newNodeId = newNode.node_id || newNode.id;
                if (newNodeId) {
                    // Auto-connect edge from source to new node
                    await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            source: sourceNodeId,
                            target: newNodeId,
                            type: 'hard',
                            reason: '',
                        }),
                    });
                }
            }

            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Add node at error:', err);
        }
    };

    // Connect two existing nodes with an edge
    const handleConnectNodes = async (sourceId: string, targetId: string) => {
        try {
            await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source: sourceId,
                    target: targetId,
                    type: 'hard',
                    reason: '',
                }),
            });
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Connect error:', err);
        }
    };

    const handleAddNode = async (nodeData: {
        label: string;
        description: string;
        phase: string;
        category: string;
        checklist: string[];
    }) => {
        try {
            await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...nodeData,
                    pos_x: 400 + Math.random() * 200,
                    pos_y: 400 + Math.random() * 200,
                }),
            });
            setShowAddDialog(false);
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Add node error:', err);
        }
    };

    const handleDeleteNode = async () => {
        const idsToDelete = selectedNodeIds.size > 0 ? Array.from(selectedNodeIds) : (selectedNodeId ? [selectedNodeId] : []);
        if (idsToDelete.length === 0) return;
        const msg = idsToDelete.length > 1
            ? `${idsToDelete.length}個のノードを削除しますか？`
            : 'このノードを削除しますか？';
        if (!confirm(msg)) return;
        try {
            await Promise.all(idsToDelete.map(id =>
                fetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${id}`, {
                    method: 'DELETE',
                })
            ));
            setSelectedNodeId(null);
            setSelectedNodeIds(new Set());
            setUndoCount(prev => prev + idsToDelete.length);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Delete error:', err);
        }
    };

    const handleUndo = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/mindmap/projects/${projectId}/undo`, {
                method: 'POST',
            });
            if (res.ok) {
                setUndoCount(prev => Math.max(0, prev - 1));
                showSaveStatus();
                loadProject(false);
            }
        } catch (err) {
            console.error('Undo error:', err);
        }
    };

    // Computed values
    const selectedNode = useMemo(() => {
        return activeNodes.find(n => n.id === selectedNodeId) || null;
    }, [activeNodes, selectedNodeId]);

    const selectedNodeEdges = useMemo(() => {
        if (!selectedNodeId) return { incoming: [] as EdgeData[], outgoing: [] as EdgeData[] };
        const incoming = activeEdges.filter(e => e.target === selectedNodeId);
        const outgoing = activeEdges.filter(e => e.source === selectedNodeId);
        return { incoming, outgoing };
    }, [activeEdges, selectedNodeId]);

    // Keyboard Shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Ignore if input/textarea is focused
            if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') return;

            if (e.key === 'z' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                handleUndo();
            } else if (e.key === 's' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                showSaveStatus(); // Manual save is just visual since we auto-save
            } else if (e.key === 'Delete' || e.key === 'Backspace') {
                if (selectedNodeId) handleDeleteNode();
            } else if (e.key === 'n' || e.key === 'N') {
                e.preventDefault();
                if (selectedNodeId) {
                    // Add child
                    const parent = activeNodes.find(n => n.id === selectedNodeId);
                    if (parent) {
                        handleAddNodeAt('新規ノード', parent.position.x + 200, parent.position.y, selectedNodeId);
                    }
                } else {
                    // Add independent
                    setShowAddDialog(true);
                }
            } else if (e.key === ' ' || e.key === 'Space') {
                e.preventDefault();
                if (selectedNodeId) {
                    // Trigger edit mode visually or focus
                    // For now, we rely on double-click, but we could trigger it via state if CustomNode supported it
                    // TODO: Pass 'forceEdit' to CustomNode?
                }
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedNodeId, activeNodes, undoCount]); // Dependencies for actions

    // Context Menu Handlers
    const handleNodeContextMenu = useCallback((event: React.MouseEvent, nodeId: string) => {
        setContextMenu({
            x: event.clientX,
            y: event.clientY,
            type: 'node',
            targetId: nodeId,
        });
        setSelectedNodeId(nodeId);
    }, []);

    const handlePaneContextMenu = useCallback((event: React.MouseEvent) => {
        setContextMenu({
            x: event.clientX,
            y: event.clientY,
            type: 'pane',
        });
        setSelectedNodeId(null);
    }, []);

    const handleCloseContextMenu = useCallback(() => {
        setContextMenu(null);
    }, []);

    const { visibleNodes, visibleEdges, descendantCounts } = useMemo(() => {
        // 1. Build adjacency list for efficient traversal
        const adjacency = new Map<string, string[]>();
        activeEdges.forEach(e => {
            if (!adjacency.has(e.source)) adjacency.set(e.source, []);
            adjacency.get(e.source)!.push(e.target);
        });

        // 2. Identify hidden nodes (descendants of collapsed nodes)
        const hiddenNodeIds = new Set<string>();
        const counts = new Map<string, number>();

        // Helper to get all descendants
        const getDescendants = (rootId: string): Set<string> => {
            const descendants = new Set<string>();
            const queue = [rootId];
            while (queue.length > 0) {
                const current = queue.shift()!;
                const children = adjacency.get(current) || [];
                for (const child of children) {
                    if (!descendants.has(child)) {
                        descendants.add(child);
                        queue.push(child);
                    }
                }
            }
            return descendants;
        };

        // For each collapsed node, hide its descendants
        collapsedNodeIds.forEach(collapsedId => {
            const descendants = getDescendants(collapsedId);
            descendants.forEach(d => hiddenNodeIds.add(d));
            counts.set(collapsedId, descendants.size);
        });

        // 3. Filter nodes
        const nodes = activeNodes.filter(n => {
            // Apply phase/category filters
            if (!filterPhases.has(n.phase) || !filterCategories.has(n.category)) return false;
            // Apply collapse filter
            if (hiddenNodeIds.has(n.id)) return false;
            return true;
        });

        // 4. Filter edges
        const visibleNodeIds = new Set(nodes.map(n => n.id));
        const edges = activeEdges.filter(e => {
            // Both source and target must be visible
            return visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target);
        });

        return { visibleNodes: nodes, visibleEdges: edges, descendantCounts: counts };
    }, [activeNodes, activeEdges, filterPhases, filterCategories, collapsedNodeIds]);

    const togglePhase = (phase: string) => {
        setFilterPhases(prev => {
            const next = new Set(prev);
            if (next.has(phase)) next.delete(phase);
            else next.add(phase);
            return next;
        });
    };

    const toggleCategory = (cat: string) => {
        setFilterCategories(prev => {
            const next = new Set(prev);
            if (next.has(cat)) next.delete(cat);
            else next.add(cat);
            return next;
        });
    };

    const getNodeLabel = (nodeId: string) => {
        return activeNodes.find(n => n.id === nodeId)?.label || nodeId;
    };

    const completedCount = activeNodes.filter(n => n.status === '決定済み').length;
    const progressPercent = activeNodes.length > 0 ? Math.round(completedCount / activeNodes.length * 100) : 0;

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[var(--background)]">
                <div className="text-center">
                    <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                    <p className="text-[var(--muted)] text-sm">プロジェクトを読み込み中...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen flex flex-col bg-[var(--canvas-bg)]">
            {/* Header */}
            <header className="border-b border-[var(--border)] bg-white/80 backdrop-blur-sm sticky top-0 z-50">
                <div className="max-w-full mx-auto px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Link href="/mindmap" className="flex items-center gap-2 text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                            <ArrowLeft className="w-4 h-4" />
                            <span className="text-sm">ダッシュボード</span>
                        </Link>
                        <div className="w-px h-6 bg-[var(--border)]" />
                        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
                            <Building2 className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="text-lg font-bold text-[var(--foreground)]">
                                {project?.name || 'プロジェクト'}
                            </h1>
                            <p className="text-[10px] text-[var(--muted)]">
                                🗂️ {completedCount}/{activeNodes.length} 完了 ({progressPercent}%)
                            </p>
                        </div>
                    </div>

                    {/* Progress bar + save status */}
                    <div className="flex items-center gap-4">
                        {saveStatus !== 'idle' && (
                            <span className={`text-xs font-medium transition-opacity ${saveStatus === 'saving' ? 'text-amber-500' : 'text-green-600'
                                }`}>
                                {saveStatus === 'saving' ? '保存中...' : '✓ 保存済み'}
                            </span>
                        )}
                        <div className="flex items-center gap-2">
                            <div className="w-32 h-2 bg-[var(--border)] rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-gradient-to-r from-violet-500 to-fuchsia-500 rounded-full transition-all duration-500"
                                    style={{ width: `${progressPercent}%` }}
                                />
                            </div>
                            <span className="text-xs text-[var(--muted)]">{progressPercent}%</span>
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <div className="flex-1 flex overflow-hidden">
                {/* Left Sidebar */}
                <aside className="w-64 border-r border-[var(--border)] bg-white/50 flex flex-col overflow-y-auto">
                    {/* Next Actions */}
                    {nextActions.length > 0 && (
                        <div className="p-3 border-b border-[var(--border)]">
                            <h4 className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider mb-2">
                                🎯 次の決定事項
                            </h4>
                            <div className="space-y-1">
                                {nextActions.slice(0, 5).map(action => (
                                    <button
                                        key={action.node_id}
                                        onClick={() => setSelectedNodeId(action.node_id)}
                                        className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-[var(--background)] transition-colors"
                                    >
                                        <span className="text-[var(--foreground)]">{action.label}</span>
                                        <span className="block text-[var(--muted)] text-[10px]">{action.phase}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Goal Search */}
                    <div className="p-3 border-b border-[var(--border)]">
                        <GoalSearchBar
                            nodes={activeNodes}
                            onSearch={handleGoalSearch}
                            onClear={clearHighlight}
                            highlightedCount={highlightedNodes.size}
                        />
                    </div>

                    {/* Filters */}
                    <div className="p-3 border-b border-[var(--border)]">
                        <button
                            onClick={() => setIsFilterOpen(!isFilterOpen)}
                            className="flex items-center justify-between w-full text-sm font-medium"
                        >
                            <span className="flex items-center gap-2">
                                <Filter className="w-4 h-4" />
                                フィルター
                            </span>
                            <ChevronDown className={`w-4 h-4 transition-transform ${isFilterOpen ? 'rotate-180' : ''}`} />
                        </button>

                        {isFilterOpen && (
                            <div className="mt-3 space-y-4 animate-fade-in">
                                <div>
                                    <h4 className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider mb-2">フェーズ</h4>
                                    <div className="space-y-1">
                                        {PHASES.map(phase => (
                                            <label key={phase} className="flex items-center gap-2 cursor-pointer text-xs hover:bg-[var(--background)] p-1 rounded">
                                                <input
                                                    type="checkbox"
                                                    checked={filterPhases.has(phase)}
                                                    onChange={() => togglePhase(phase)}
                                                    className="rounded border-[var(--border)] accent-violet-500"
                                                />
                                                {phase}
                                            </label>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <h4 className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider mb-2">カテゴリ</h4>
                                    <div className="space-y-1">
                                        {CATEGORIES.map(cat => (
                                            <label key={cat} className="flex items-center gap-2 cursor-pointer text-xs hover:bg-[var(--background)] p-1 rounded">
                                                <input
                                                    type="checkbox"
                                                    checked={filterCategories.has(cat)}
                                                    onChange={() => toggleCategory(cat)}
                                                    className="rounded border-[var(--border)]"
                                                />
                                                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[cat] }} />
                                                {cat}
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Legend */}
                    <div className="p-3 border-b border-[var(--border)]">
                        <h4 className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider mb-2">凡例</h4>
                        <div className="space-y-1.5 text-xs text-[var(--muted)]">
                            <div className="flex items-center gap-2">
                                <div className="w-8 h-0.5 bg-[var(--edge-hard)]" />
                                <span>必須依存 (hard)</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-8 h-0.5 border-t-2 border-dashed" style={{ borderColor: 'var(--edge-soft)' }} />
                                <span>推奨依存 (soft)</span>
                            </div>
                        </div>
                        <div className="mt-3 space-y-1 text-xs">
                            {CATEGORIES.map(cat => (
                                <div key={cat} className="flex items-center gap-2">
                                    <span className="w-3 h-3 rounded" style={{ backgroundColor: CATEGORY_COLORS[cat] }} />
                                    <span className="text-[var(--muted)]">{cat}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Stats */}
                    <div className="p-3 text-xs text-[var(--muted)]">
                        <p>{visibleNodes.length} / {activeNodes.length} ノード表示</p>
                        <p>{visibleEdges.length} 依存関係</p>
                        {isEditMode && (
                            <p className="mt-1 text-violet-600 font-medium">✏️ 編集モード</p>
                        )}
                    </div>
                </aside>

                {/* Canvas */}
                <div className="flex-1 relative">
                    <EditToolbar
                        isEditMode={isEditMode}
                        isProjectMode={true}
                        onToggleEditMode={() => setIsEditMode(!isEditMode)}
                        onAddNode={() => setShowAddDialog(true)}
                        onDeleteNode={handleDeleteNode}
                        onUndo={handleUndo}
                        hasSelectedNode={!!selectedNodeId}
                        canUndo={undoCount > 0}
                    />

                    <ReactFlowProvider>
                        <MindmapCanvas
                            nodes={visibleNodes}
                            edges={visibleEdges}
                            selectedNodeId={selectedNodeId}
                            selectedNodeIds={selectedNodeIds}
                            highlightedNodes={highlightedNodes}
                            highlightedEdges={highlightedEdges}
                            onNodeSelect={setSelectedNodeId}
                            onSelectionChange={handleSelectionChange}
                            categoryColors={CATEGORY_COLORS}
                            isEditMode={isEditMode}
                            onNodeDragStop={handleNodeDragStop}
                            onAddNodeAt={handleAddNodeAt}
                            onConnectNodes={handleConnectNodes}
                            collapsedNodeIds={collapsedNodeIds}
                            descendantCounts={descendantCounts}
                            onNodeLabelChange={handleNodeLabelChange}
                            onNodeCollapse={handleNodeCollapse}
                            onNodeContextMenu={handleNodeContextMenu}
                            onPaneContextMenu={handlePaneContextMenu}
                        />
                    </ReactFlowProvider>
                </div>

                {/* Batch Selection Toolbar */}
                {selectedNodeIds.size > 1 && (
                    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-40 bg-white/95 backdrop-blur-sm border border-[var(--border)] rounded-xl shadow-2xl px-5 py-3 flex items-center gap-4">
                        <span className="text-sm font-medium text-[var(--foreground)]">
                            {selectedNodeIds.size} 個選択中
                        </span>
                        <div className="w-px h-6 bg-[var(--border)]" />
                        <div className="flex items-center gap-2">
                            <span className="text-xs text-[var(--muted)]">一括変更:</span>
                            {['未着手', '検討中', '決定済み'].map(s => (
                                <button
                                    key={s}
                                    onClick={() => handleBatchStatusChange(s)}
                                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${s === '決定済み' ? 'bg-green-50 text-green-700 hover:bg-green-100 border border-green-200'
                                        : s === '検討中' ? 'bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200'
                                            : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'
                                        }`}
                                >
                                    {s}
                                </button>
                            ))}
                        </div>
                        {isEditMode && (
                            <>
                                <div className="w-px h-6 bg-[var(--border)]" />
                                <button
                                    onClick={handleDeleteNode}
                                    className="px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 rounded-lg transition-colors"
                                >
                                    削除
                                </button>
                            </>
                        )}
                        <button
                            onClick={() => setSelectedNodeIds(new Set())}
                            className="ml-2 text-[var(--muted)] hover:text-[var(--foreground)] text-xs"
                        >
                            ✕ 解除
                        </button>
                    </div>
                )}

                {/* Right Detail Panel */}
                {selectedNode && (
                    <aside className="w-96 border-l border-[var(--border)] bg-white/50 overflow-y-auto">
                        <NodeDetailPanel
                            node={selectedNode}
                            incomingEdges={selectedNodeEdges.incoming}
                            outgoingEdges={selectedNodeEdges.outgoing}
                            getNodeLabel={getNodeLabel}
                            categoryColor={CATEGORY_COLORS[selectedNode.category] || '#6b7280'}
                            onClose={() => setSelectedNodeId(null)}
                            onNavigate={(nodeId) => setSelectedNodeId(nodeId)}
                            isEditMode={isEditMode}
                            onStatusChange={handleStatusChange}
                        />
                    </aside>
                )}
            </div>

            {/* Context Menu */}
            {contextMenu && (
                <ContextMenu
                    x={contextMenu.x}
                    y={contextMenu.y}
                    onClose={handleCloseContextMenu}
                    options={contextMenu.type === 'node' && contextMenu.targetId ? [
                        {
                            label: '子ノードを追加',
                            icon: <CornerDownRight className="w-4 h-4" />,
                            shortcut: 'N',
                            action: () => {
                                const parent = activeNodes.find(n => n.id === contextMenu.targetId);
                                if (parent) {
                                    handleAddNodeAt('新規ノード', parent.position.x + 250, parent.position.y, contextMenu.targetId);
                                }
                            }
                        },
                        {
                            label: collapsedNodeIds.has(contextMenu.targetId) ? '展開する' : '折りたたむ',
                            icon: collapsedNodeIds.has(contextMenu.targetId) ? <Maximize2 className="w-4 h-4" /> : <Minimize2 className="w-4 h-4" />,
                            action: () => handleNodeCollapse(contextMenu.targetId!)
                        },
                        {
                            label: '削除',
                            icon: <Trash2 className="w-4 h-4" />,
                            danger: true,
                            shortcut: 'Del',
                            action: handleDeleteNode
                        }
                    ] : [
                        {
                            label: 'ここにノードを追加',
                            icon: <Plus className="w-4 h-4" />,
                            action: () => setShowAddDialog(true) // Ideal: use screen pos, but dialog doesn't support it yet
                        }
                    ]}
                />
            )}

            {/* Add Node Dialog */}
            {showAddDialog && (
                <AddNodeDialog
                    onAdd={handleAddNode}
                    onClose={() => setShowAddDialog(false)}
                />
            )}
        </div>
    );
}
