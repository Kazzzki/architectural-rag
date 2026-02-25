'use client';
import { authFetch } from '@/lib/api';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ReactFlowProvider, Connection, useReactFlow } from 'reactflow';
import MindmapCanvas from '../../../components/mindmap/MindmapCanvas';
import NodeDetailPanel from '../../../components/mindmap/NodeDetailPanel';
import GoalSearchBar from '../../../components/mindmap/GoalSearchBar';
import EditToolbar from '../../../components/mindmap/EditToolbar';
import AddNodeDialog from '../../../components/mindmap/AddNodeDialog';
import ContextMenu from '../../../components/mindmap/ContextMenu';
import IntegratedSidebar from '../../../components/mindmap/IntegratedSidebar'; // New
import { useAutoRag } from '../../../hooks/useAutoRag'; // New
import { Building2, ArrowLeft, Filter, ChevronDown, Plus, Edit2, Trash2, CornerDownRight, Minimize2, Maximize2, Sidebar } from 'lucide-react';
import Link from 'next/link';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

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
    ragResults?: any[]; // Store RAG results in node data
    chatHistory?: any[]; // Store Chat history
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

    // Sidebar state
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [sidebarWidth, setSidebarWidth] = useState(320);
    const isDraggingSidebarRef = useRef(false);

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!isDraggingSidebarRef.current) return;
            const newWidth = document.body.clientWidth - e.clientX;
            const clampedWidth = Math.max(300, Math.min(newWidth, 800));
            setSidebarWidth(clampedWidth);
        };
        const handleMouseUp = () => {
            if (isDraggingSidebarRef.current) {
                isDraggingSidebarRef.current = false;
                document.body.style.cursor = '';
            }
        };
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            document.body.style.cursor = '';
        };
    }, []);

    const startSidebarResize = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        isDraggingSidebarRef.current = true;
        document.body.style.cursor = 'ew-resize';
    }, []);

    const activeNodes = project?.nodes || [];
    const activeEdges = project?.edges || [];

    // Load project data
    const loadProject = useCallback(async (isInitial = false) => {
        if (isInitial) setLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}`);
            if (!res.ok) throw new Error('Project not found');
            const data = await res.json();
            setProject(data);

            // Load next actions
            const actionsRes = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/next-actions`);
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

    // ─────────────────────────────────────────────────────────────
    // Integrated Sidebar Logic
    // ─────────────────────────────────────────────────────────────

    const selectedNode = useMemo(() => {
        return activeNodes.find(n => n.id === selectedNodeId) || null;
    }, [activeNodes, selectedNodeId]);

    // Auto-RAG Hook
    const { isSearching } = useAutoRag({
        projectId,
        selectedNode,
        onResultsFound: (nodeId, data) => {
            // Update node with RAG results
            setProject(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    nodes: prev.nodes.map(n =>
                        n.id === nodeId
                            ? { ...n, ragResults: data.results }
                            : n
                    )
                };
            });
            // Persist to backend (optional, if we want to save RAG results permanently)
            // For now, we keep it in memory or could save as special metadata
        }
    });

    // Chat Handler
    const handleChatSend = async (message: string) => {
        if (!selectedNodeId) return;

        // Add user message
        const newMessage = { role: 'user', content: message };

        setProject(prev => {
            if (!prev) return null;
            return {
                ...prev,
                nodes: prev.nodes.map(n => {
                    if (n.id === selectedNodeId) {
                        return { ...n, chatHistory: [...(n.chatHistory || []), newMessage] };
                    }
                    return n;
                })
            };
        });

        // Mock AI Response (Replace with real API call if needed)
        // Ideally, call /api/mindmap/ai/chat
        setTimeout(() => {
            const aiMessage = { role: 'assistant', content: `AIの回答モック: "${message}" についてですね。このノードのコンテキストとRAG結果に基づいて回答します。` };
            setProject(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    nodes: prev.nodes.map(n => {
                        if (n.id === selectedNodeId) {
                            return { ...n, chatHistory: [...(n.chatHistory || []), aiMessage] };
                        }
                        return n;
                    })
                };
            });
        }, 1000);
    };

    // Drag & Drop Knowledge to Canvas
    const onDragStartKnowledge = (event: React.DragEvent, item: any) => {
        event.dataTransfer.setData('application/json', JSON.stringify({
            type: 'knowledge',
            sourceId: selectedNodeId,
            content: item.content,
            source: item.source
        }));
        event.dataTransfer.effectAllowed = 'copy';
    };

    const onDropOnCanvas = useCallback(async (event: React.DragEvent) => {
        event.preventDefault();

        const dataStr = event.dataTransfer.getData('application/json');
        if (!dataStr) return;

        try {
            const data = JSON.parse(dataStr);
            if (data.type === 'knowledge' && data.sourceId) {
                console.log("Dropped knowledge:", data);
            }
        } catch (e) {
            console.error("Drop parse error", e);
        }
    }, [/*handleAddNodeAt*/]);

    // ─────────────────────────────────────────────────────────────

    // Goal search
    const handleGoalSearch = async (nodeId: string) => {
        if (!project) return;
        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/tree/${project.template_id}/${nodeId}`);
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
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
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
                authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
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
        } else {
            setSelectedNodeId(null);
        }
    }, []);

    const handleNodeDragStop = async (nodeId: string, x: number, y: number) => {
        // Optimistic update
        setProject(prev => {
            if (!prev) return null;
            return {
                ...prev,
                nodes: prev.nodes.map(n =>
                    n.id === nodeId
                        ? { ...n, position: { x, y } }
                        : n
                )
            };
        });

        try {
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pos_x: x, pos_y: y }),
            });
            showSaveStatus();
        } catch (err) {
            console.error('Drag error:', err);
            // Revert on error (optional, but good practice)
            loadProject(false);
        }
    };

    const handleNodeLabelChange = async (nodeId: string, newLabel: string) => {
        try {
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
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

            const res = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes`, {
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
                    await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges`, {
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
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges`, {
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

    const handleEdgeUpdate = async (oldEdge: EdgeData, newConnection: Connection) => {
        if (!newConnection.source || !newConnection.target) return;
        try {
            // Delete old edge
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges/${oldEdge.id}`, {
                method: 'DELETE',
            });
            // Create new edge
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source: newConnection.source,
                    target: newConnection.target,
                    type: oldEdge.type,
                    reason: oldEdge.reason,
                }),
            });
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Edge update error:', err);
        }
    };

    const handleEdgesDelete = async (edgeIds: string[]) => {
        if (edgeIds.length === 0) return;
        try {
            await Promise.all(edgeIds.map(id =>
                authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges/${id}`, {
                    method: 'DELETE',
                })
            ));
            setUndoCount(prev => prev + edgeIds.length);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Edge delete error:', err);
        }
    };

    const handleNodesDelete = async (nodeIds: string[]) => {
        if (nodeIds.length === 0) return;
        try {
            await Promise.all(nodeIds.map(id =>
                authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${id}`, {
                    method: 'DELETE',
                })
            ));
            setSelectedNodeId(null);
            setSelectedNodeIds(new Set());
            setUndoCount(prev => prev + nodeIds.length);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Delete error:', err);
        }
    };

    const handleNodeUpdate = async (nodeId: string, updates: Partial<ProcessNode>) => {
        try {
            // Optimistic update for UI responsiveness
            setProject(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    nodes: prev.nodes.map(n =>
                        n.id === nodeId ? { ...n, ...updates } : n
                    )
                };
            });

            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            // Background reload to ensure consistency
            loadProject(false);
        } catch (err) {
            console.error('Node update error:', err);
            loadProject(false);
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
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes`, {
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
        try {
            await Promise.all(idsToDelete.map(id =>
                authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${id}`, {
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
            const res = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/undo`, {
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

    // AI Copilot Handler
    const handleAiAction = async (action: 'summarize' | 'expand' | 'rag' | 'investigate', nodeId: string, content: string) => {
        const node = activeNodes.find(n => n.id === nodeId);
        if (!node) return;

        showSaveStatus();

        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/ai/action`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action,
                    nodeId,
                    content: content || node.label,
                    context: {
                        projectId,
                        projectContext: project?.description,
                        nodeContext: node
                    }
                }),
            });

            if (!res.ok) throw new Error('AI API failed');

            const data = await res.json();

            if ((action === 'expand' || action === 'investigate') && data.text) {
                // Add to chat history
                const title = action === 'expand' ? 'アイデア拡張' : '調査レポート';
                const aiMessage = {
                    role: 'assistant',
                    content: `【${title}: ${node.label}】\n\n${data.text}`
                };

                setProject(prev => {
                    if (!prev) return null;
                    return {
                        ...prev,
                        nodes: prev.nodes.map(n => {
                            if (n.id === nodeId) {
                                return { ...n, chatHistory: [...(n.chatHistory || []), aiMessage] };
                            }
                            return n;
                        })
                    };
                });

                // Persist chat history
                const updatedChatHistory = [...(node.chatHistory || []), aiMessage];
                await handleNodeUpdate(nodeId, { chatHistory: updatedChatHistory });

                // Open sidebar
                setIsSidebarOpen(true);
            } else if ((action === 'summarize' || action === 'rag') && data.text) {
                const newDescription = (node.description ? node.description + '\n\n' : '') + data.text;
                await handleNodeUpdate(nodeId, { description: newDescription });
                setSelectedNodeId(nodeId);


            }

            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('AI Action error:', err);
            alert('AI処理に失敗しました。');
        }
    };


    const selectedNodeEdges = useMemo(() => {
        if (!selectedNodeId) return { incoming: [] as EdgeData[], outgoing: [] as EdgeData[] };
        const incoming = activeEdges.filter(e => e.target === selectedNodeId);
        const outgoing = activeEdges.filter(e => e.source === selectedNodeId);
        return { incoming, outgoing };
    }, [activeEdges, selectedNodeId]);

    // Keyboard Shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') return;

            if (e.key === 'z' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                handleUndo();
            } else if (e.key === 's' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                showSaveStatus();
            } else if (e.key === 'n' || e.key === 'N') {
                e.preventDefault();
                if (selectedNodeId) {
                    const parent = activeNodes.find(n => n.id === selectedNodeId);
                    if (parent) {
                        handleAddNodeAt('新規ノード', parent.position.x + 200, parent.position.y, selectedNodeId);
                    }
                } else {
                    setShowAddDialog(true);
                }
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedNodeId, activeNodes, undoCount]);

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
        const adjacency = new Map<string, string[]>();
        activeEdges.forEach(e => {
            if (!adjacency.has(e.source)) adjacency.set(e.source, []);
            adjacency.get(e.source)!.push(e.target);
        });

        const hiddenNodeIds = new Set<string>();
        const counts = new Map<string, number>();

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

        collapsedNodeIds.forEach(collapsedId => {
            const descendants = getDescendants(collapsedId);
            descendants.forEach(d => hiddenNodeIds.add(d));
            counts.set(collapsedId, descendants.size);
        });

        const nodes = activeNodes.filter(n => {
            if (!filterPhases.has(n.phase) || !filterCategories.has(n.category)) return false;
            if (hiddenNodeIds.has(n.id)) return false;
            return true;
        });

        const visibleNodeIds = new Set(nodes.map(n => n.id));
        const edges = activeEdges.filter(e => {
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

                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                            className={`p-2 rounded-md transition-colors ${isSidebarOpen ? 'bg-blue-100 text-blue-600' : 'text-gray-500 hover:bg-gray-100'
                                }`}
                            title="サイドバー切り替え"
                        >
                            <Sidebar className="w-5 h-5" />
                        </button>

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

            <div className="flex-1 flex overflow-hidden">
                <aside className="w-64 border-r border-[var(--border)] bg-white/50 flex flex-col overflow-y-auto hidden md:flex">
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

                    <div className="p-3 border-b border-[var(--border)]">
                        <GoalSearchBar
                            nodes={activeNodes}
                            onSearch={handleGoalSearch}
                            onClear={clearHighlight}
                            highlightedCount={highlightedNodes.size}
                        />
                    </div>

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
                                                    className="rounded border-[var(--border)] accent-violet-500"
                                                />
                                                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[cat] }} />
                                                {cat}
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </aside>

                <main className="flex-1 relative bg-dot-pattern"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={async (e) => {
                        e.preventDefault();
                        const dataStr = e.dataTransfer.getData('application/json');
                        if (!dataStr) return;
                        try {
                            const data = JSON.parse(dataStr);
                            if (data.type === 'knowledge' && data.sourceId) {
                                const sourceNode = activeNodes.find(n => n.id === data.sourceId);
                                const x = sourceNode ? sourceNode.position.x + 300 : 400;
                                const y = sourceNode ? sourceNode.position.y : 400;

                                await handleAddNodeAt(
                                    data.content.substring(0, 20) + "...", // Short label
                                    x,
                                    y,
                                    data.sourceId
                                );
                            }
                        } catch (err) {
                            console.error("Drop error", err);
                        }
                    }}
                >
                    <ReactFlowProvider>
                        <MindmapCanvas
                            nodes={visibleNodes}
                            edges={visibleEdges}
                            allEdges={activeEdges}
                            selectedNodeId={selectedNodeId}
                            selectedNodeIds={selectedNodeIds}
                            highlightedNodes={highlightedNodes}
                            highlightedEdges={highlightedEdges}
                            onNodeSelect={setSelectedNodeId}
                            onSelectionChange={(ids) => setSelectedNodeIds(new Set(ids))}
                            categoryColors={CATEGORY_COLORS}
                            isEditMode={isEditMode}
                            onNodeDragStop={handleNodeDragStop}
                            onAddNodeAt={handleAddNodeAt}
                            onConnectNodes={handleConnectNodes}
                            onEdgeUpdate={handleEdgeUpdate}
                            onEdgesDelete={handleEdgesDelete}
                            onNodesDelete={handleNodesDelete}
                            collapsedNodeIds={collapsedNodeIds}
                            descendantCounts={descendantCounts}
                            onNodeLabelChange={handleNodeLabelChange}
                            onNodeCollapse={handleNodeCollapse}
                            onNodeContextMenu={handleNodeContextMenu}
                            onPaneContextMenu={handlePaneContextMenu}
                            onAiAction={handleAiAction}
                        />
                        <div className="absolute top-4 right-4 flex flex-col gap-2">
                            <EditToolbar
                                isEditMode={isEditMode}
                                isProjectMode={true}
                                onToggleEditMode={() => setIsEditMode(!isEditMode)}
                                onAddNode={() => setShowAddDialog(true)}
                                onDeleteNode={handleDeleteNode}
                                onInvestigate={() => selectedNodeId && handleAiAction('investigate', selectedNodeId, '')}
                                onUndo={handleUndo}
                                hasSelectedNode={!!selectedNodeId || selectedNodeIds.size > 0}
                                canUndo={undoCount > 0}
                            />
                        </div>
                    </ReactFlowProvider>
                </main>

                {isSidebarOpen && (
                    <aside className="border-l border-[var(--border)] bg-white/50 flex flex-col shadow-xl z-10 relative flex-shrink-0" style={{ width: sidebarWidth }}>
                        {/* Resizer Handle */}
                        <div
                            className="absolute left-0 top-0 bottom-0 w-3 cursor-ew-resize hover:bg-blue-400/20 z-50 flex items-center justify-center group -ml-1.5"
                            onMouseDown={startSidebarResize}
                        >
                            <div className="w-1 h-12 bg-gray-300 rounded-full group-hover:bg-blue-500 transition-colors" />
                        </div>
                        <div className="flex-1 w-full overflow-hidden flex flex-col">
                            <IntegratedSidebar
                                selectedNode={selectedNode}
                                knowledge={selectedNode?.ragResults || []}
                                chatHistory={selectedNode?.chatHistory || []}
                                isSearching={isSearching}
                                onChatSend={handleChatSend}
                                onDragStart={onDragStartKnowledge}
                            />
                        </div>
                    </aside>
                )}
            </div>

            {showAddDialog && (
                <AddNodeDialog
                    onClose={() => setShowAddDialog(false)}
                    onAdd={handleAddNode}
                />
            )}

            {contextMenu && (
                <ContextMenu
                    x={contextMenu.x}
                    y={contextMenu.y}
                    options={[
                        ...(contextMenu.type === 'node' ? [
                            { label: '編集', icon: <Edit2 className="w-4 h-4" />, action: () => { handleCloseContextMenu(); /* TODO: Edit */ } },
                            { label: '削除', icon: <Trash2 className="w-4 h-4" />, action: () => { handleDeleteNode(); handleCloseContextMenu(); }, danger: true },
                            {
                                label: '子ノード追加', icon: <CornerDownRight className="w-4 h-4" />, action: () => {
                                    if (selectedNodeId) {
                                        const parent = activeNodes.find(n => n.id === selectedNodeId);
                                        if (parent) handleAddNodeAt('新規ノード', parent.position.x + 200, parent.position.y, selectedNodeId);
                                    }
                                    handleCloseContextMenu();
                                }
                            }
                        ] : []),
                        ...(contextMenu.type === 'pane' ? [
                            { label: '新規ノード作成', icon: <Plus className="w-4 h-4" />, action: () => { setShowAddDialog(true); handleCloseContextMenu(); } }
                        ] : [])
                    ]}
                    onClose={handleCloseContextMenu}
                />
            )}
        </div>
    );
}
