'use client';
import { authFetch } from '@/lib/api';
import dagre from 'dagre';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ReactFlowProvider, Connection, useReactFlow } from 'reactflow';
import MindmapCanvas from '../../../components/mindmap/MindmapCanvas';
import NodeDetailPanel from '../../../components/mindmap/NodeDetailPanel';
import GoalSearchBar from '../../../components/mindmap/GoalSearchBar';
import EditToolbar from '../../../components/mindmap/EditToolbar';
import AddNodeDialog from '../../../components/mindmap/AddNodeDialog';
import EditNodeDialog from '../../../components/mindmap/EditNodeDialog';
import ContextMenu from '../../../components/mindmap/ContextMenu';
import EditEdgeDialog from '../../../components/mindmap/EditEdgeDialog';
import IntegratedSidebar from '../../../components/mindmap/IntegratedSidebar'; // New
import FilterPanel from '../../../components/mindmap/FilterPanel';
import MobileMindmapControls from '../../../components/mindmap/MobileMindmapControls';
import SaveStatusOverlay from '../../../components/mindmap/SaveStatusOverlay';
import KeyboardShortcutsModal from '../../../components/mindmap/KeyboardShortcutsModal'; // New
import GapAdvisorModal from '../../../components/mindmap/GapAdvisorModal'; // New
import { useAutoRag } from '../../../hooks/useAutoRag'; // New
import { Building2, ArrowLeft, Filter, ChevronDown, Plus, Edit2, Trash2, CornerDownRight, Minimize2, Maximize2, Sidebar, X, GitBranch, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { PHASES, CATEGORIES, CATEGORY_COLORS } from '@/lib/mindmapConstants';

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
    technical_conditions?: string;
    legal_requirements?: string;
    nodes: ProcessNode[];
    edges: EdgeData[];
}


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
    const [showEditDialog, setShowEditDialog] = useState(false);
    const [showEdgeDialog, setShowEdgeDialog] = useState(false);
    const [nodeToEdit, setNodeToEdit] = useState<ProcessNode | null>(null);
    const [edgeToEdit, setEdgeToEdit] = useState<EdgeData | null>(null);
    const [pendingConnection, setPendingConnection] = useState<{ source: string, target: string } | null>(null);
    const [undoCount, setUndoCount] = useState(0);
    const [nextActions, setNextActions] = useState<any[]>([]);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'dirty' | 'error'>('idle');
    const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
    const [contextMenu, setContextMenu] = useState<{ x: number; y: number; type: 'node' | 'pane' | 'edge'; targetId?: string } | null>(null);
    const [selectedNodeIds, setSelectedNodeIds] = useState<Set<string>>(new Set());
    const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
    const [pulsingNodeId, setPulsingNodeId] = useState<string | null>(null);
    const [rfInstance, setRfInstance] = useState<any>(null);
    const [forceChatTab, setForceChatTab] = useState<string | null>(null);
    const [searchResults, setSearchResults] = useState<string[]>([]);
    const [currentSearchIndex, setCurrentSearchIndex] = useState(0);
    const [showShortcutsModal, setShowShortcutsModal] = useState(false);
    const [showGapAdvisorModal, setShowGapAdvisorModal] = useState(false);
    const [editingNodeId, setEditingNodeId] = useState<string | null>(null);

    // Sidebar state
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [isSidebarMaximized, setIsSidebarMaximized] = useState(false);
    const [sidebarWidth, setSidebarWidth] = useState(320);
    const isDraggingSidebarRef = useRef(false);

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!isDraggingSidebarRef.current) return;
            const newWidth = document.body.clientWidth - e.clientX;
            const clampedWidth = Math.max(320, Math.min(newWidth, 480));
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

    const loadNextActions = useCallback(async () => {
        try {
            const actionsRes = await authFetch(`/api/mindmap/projects/${projectId}/next-actions`);
            if (actionsRes.ok) {
                setNextActions(await actionsRes.json());
            }
        } catch (err) {
            console.error('Next actions error:', err);
        }
    }, [projectId]);

    // Load project data
    const loadProject = useCallback(async (isInitial = false) => {
        if (isInitial) setLoading(true);
        try {
            const res = await authFetch(`/api/mindmap/projects/${projectId}`);
            if (!res.ok) throw new Error('Project not found');
            const data = await res.json();
            setProject(data);
            if (data.delta_count !== undefined) {
                setUndoCount(data.delta_count);
            }

            // Load next actions
            loadNextActions();
        } catch (err) {
            console.error('Project load error:', err);
            router.push('/mindmap');
        } finally {
            if (isInitial) setLoading(false);
        }
    }, [projectId, router, loadNextActions]);

    useEffect(() => {
        loadProject(true);
    }, [loadProject]);

    // Auto-save status display
    const showSaveStatus = useCallback((isError = false) => {
        if (isError) {
            setSaveStatus('error');
            return;
        }
        setSaveStatus('saved');
        setLastSavedAt(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        setTimeout(() => setSaveStatus('idle'), 3000);
    }, []);

    const markDirty = useCallback(() => {
        if (saveStatus !== 'saving') {
            setSaveStatus('dirty');
        }
    }, [saveStatus]);

    // Enhanced beforeunload to warn about unsaved changes
    useEffect(() => {
        const handleBeforeUnload = (e: BeforeUnloadEvent) => {
            if (saveStatus === 'dirty' || saveStatus === 'saving') {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', handleBeforeUnload);
        return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }, [saveStatus]);

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
        if (!selectedNodeId || !selectedNode) return;

        const userMsg = { role: 'user' as const, content: message };
        setProject(prev => {
            if (!prev) return null;
            return {
                ...prev,
                nodes: prev.nodes.map(n =>
                    n.id === selectedNodeId
                        ? { ...n, chatHistory: [...(n.chatHistory || []), userMsg] }
                        : n
                ),
            };
        });

        try {
            const res = await authFetch(`/api/mindmap/ai/action`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'rag',
                    nodeId: selectedNodeId,
                    content: message,
                    context: {
                        projectId,
                        projectContext: project?.description,
                        nodeContext: {
                            label: selectedNode.label,
                            phase: selectedNode.phase,
                            category: selectedNode.category,
                            description: selectedNode.description,
                        }
                    }
                }),
            });
            if (!res.ok) throw new Error('AI API failed');
            const data = await res.json();

            const aiMsg = { role: 'assistant' as const, content: data.text || 'AIからの応答を取得できませんでした' };
            setProject(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    nodes: prev.nodes.map(n =>
                        n.id === selectedNodeId
                            ? { ...n, chatHistory: [...(n.chatHistory || []), aiMsg] }
                            : n
                    ),
                };
            });
        } catch (err) {
            console.error('Chat API error:', err);
            const aiMsg = { role: 'assistant' as const, content: 'エラーが発生しました。API設定を確認してください。' };
            setProject(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    nodes: prev.nodes.map(n =>
                        n.id === selectedNodeId ? { ...n, chatHistory: [...(n.chatHistory || []), aiMsg] } : n
                    ),
                };
            });
        }
    };

    const handleSendToMap = async (message: string) => {
        try {
            const res = await authFetch(`/api/mindmap/projects/${projectId}/nodes/from-text`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: message, source_type: 'chat' })
            });
            if (!res.ok) throw new Error('Failed to create node from text');
            const data = await res.json();
            if (data.created_nodes && data.created_nodes.length > 0) {
                setProject(prev => {
                    if (!prev) return prev;
                    return {
                        ...prev,
                        nodes: [...prev.nodes, ...data.created_nodes]
                    };
                });
                window.dispatchEvent(new CustomEvent('mindmap:node-added', { detail: data.created_nodes }));
                markDirty();

                // --- Link Prediction (PR-6) ---
                for (const newNode of data.created_nodes) {
                    try {
                        const predictRes = await authFetch(`/api/mindmap/projects/${projectId}/ai/predict-links`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ new_node_id: newNode.id })
                        });
                        if (predictRes.ok) {
                            const predictData = await predictRes.json();
                            const predictions = predictData.predictions || [];
                            if (predictions.length > 0) {
                                const parentLabels = predictions.map((pid: string) => {
                                    const pNode = project?.nodes.find(n => n.id === pid);
                                    return pNode ? pNode.label : pid;
                                }).join(', ');
                                
                                if (window.confirm(`「${newNode.label}」の親として以下が推測されました。自動で関連付け（エッジ作成）を行いますか？\n\n予測された親: ${parentLabels}`)) {
                                    for (const parentId of predictions) {
                                        await authFetch(`/api/mindmap/projects/${projectId}/edges`, {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({
                                                source: parentId,
                                                target: newNode.id,
                                                type: 'soft',
                                                reason: 'AIによる自動関連付け予測'
                                            }),
                                        });
                                    }
                                    loadProject(false);
                                }
                            }
                        }
                    } catch (err) {
                        console.error("Link prediction failed", err);
                    }
                }
            } else {
                alert('ノードを抽出できませんでした。');
            }
        } catch (err) {
            console.error(err);
            alert('ノードの抽出・追加に失敗しました');
        }
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

    // Keyboard support - Consolidated below

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
            const res = await authFetch(`/api/mindmap/projects/${projectId}/reverse-tree/${nodeId}`);
            if (!res.ok) throw new Error('依存関係の取得に失敗しました');
            const data = await res.json();
            
            // トポロジカル順のノードIDリストがある場合はそれを使用
            const nodeIds = data.path_order || (data.nodes ? data.nodes.map((n: any) => n.id) : [nodeId]);
            const edgeIds = data.edges ? data.edges.map((e: any) => e.id) : [];

            setHighlightedNodes(new Set(nodeIds));
            setHighlightedEdges(new Set(edgeIds));
            setSearchResults(nodeIds);
            setCurrentSearchIndex(0);
            
            if (nodeIds.length > 0) jumpToNode(nodeIds[0]);
        } catch (err) {
            console.error('Search error:', err);
            // Fallback: 該当ノードのみハイライト
            setHighlightedNodes(new Set([nodeId]));
            jumpToNode(nodeId);
        }
    };

    const clearHighlight = () => {
        setHighlightedNodes(new Set());
        setHighlightedEdges(new Set());
        setSearchResults([]);
        setCurrentSearchIndex(0);
    };

    // New: Handle search navigation
    const jumpToNode = useCallback((nodeId: string) => {
        if (!rfInstance) return;
        const node = activeNodes.find(n => n.id === nodeId);
        if (node) {
            rfInstance.setCenter(node.position.x, node.position.y, { zoom: 1.2, duration: 800 });

            // T8: Expand parents if hidden
            const parentsToExpand = new Set<string>();
            const findParents = (targetId: string) => {
                activeEdges.forEach(e => {
                    if (e.target === targetId) {
                        parentsToExpand.add(e.source);
                        findParents(e.source);
                    }
                });
            };
            findParents(nodeId);
            if (parentsToExpand.size > 0) {
                setCollapsedNodeIds(prev => {
                    const next = new Set(prev);
                    let changed = false;
                    parentsToExpand.forEach(p => {
                        if (next.has(p)) {
                            next.delete(p);
                            changed = true;
                        }
                    });
                    return changed ? next : prev;
                });
            }

            setSelectedNodeId(nodeId);
            setPulsingNodeId(nodeId);
            setTimeout(() => setPulsingNodeId(null), 1500);
        }
    }, [rfInstance, activeNodes, activeEdges]);

    const handleSearchNavigation = (direction: 'next' | 'prev') => {
        if (searchResults.length === 0) return;
        let nextIndex = direction === 'next' ? currentSearchIndex + 1 : currentSearchIndex - 1;
        if (nextIndex >= searchResults.length) nextIndex = 0;
        if (nextIndex < 0) nextIndex = searchResults.length - 1;

        setCurrentSearchIndex(nextIndex);
        jumpToNode(searchResults[nextIndex]);
    };

    // Node operations
    const handleStatusChange = async (nodeId: string, newStatus: string) => {
        markDirty();
        try {
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus }),
            });
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
            loadNextActions();
        } catch (err) {
            console.error('Status update error:', err);
            showSaveStatus(true);
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
            loadNextActions();
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
        if (nodeIds.length > 0) {
            setSelectedEdgeId(null);
        }
    }, []);

    const handleEdgeSelect = useCallback((edgeId: string) => {
        setSelectedEdgeId(edgeId);
        setSelectedNodeId(null);
        setSelectedNodeIds(new Set());
    }, []);

    const handleNodeDragStop = async (nodeId: string, x: number, y: number) => {
        markDirty();
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
            showSaveStatus(true);
            // Revert on error (optional, but good practice)
            loadProject(false);
        }
    };

    const handleNodeLabelChange = async (nodeId: string, newLabel: string) => {
        markDirty();
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

            const res = await authFetch(`/api/mindmap/projects/${projectId}/nodes`, {
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

    const handleConnectNodes = async (sourceId: string, targetId: string) => {
        // W2: Client-side duplicate check
        const exists = activeEdges.some(e => e.source === sourceId && e.target === targetId);
        if (exists) {
            console.warn('Edge already exists');
            return;
        }

        // Open dialog for type/reason
        setPendingConnection({ source: sourceId, target: targetId });
        setEdgeToEdit(null);
        setShowEdgeDialog(true);
    };

    const handleEdgeUpdate = async (oldEdge: EdgeData, newConnection: Connection) => {
        if (!newConnection.source || !newConnection.target) return;

        // W2: Prevent creating duplicates via update
        const exists = activeEdges.some(
            e => e.id !== oldEdge.id && e.source === newConnection.source && e.target === newConnection.target
        );
        if (exists) {
            console.warn('Target edge already exists');
            // Edge remains at old position if we don't reload, but ReactFlow might have moved it visually
            loadProject(false);
            return;
        }

        try {
            // W5: Use atomic update endpoint
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges/${oldEdge.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source: newConnection.source,
                    target: newConnection.target,
                }),
            });
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Edge update error:', err);
        }
    };

    const handleEdgeDialogConfirm = async (type: string, reason: string) => {
        try {
            if (pendingConnection) {
                // Create new edge
                await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source: pendingConnection.source,
                        target: pendingConnection.target,
                        type,
                        reason,
                    }),
                });
            } else if (edgeToEdit) {
                // Update existing edge
                await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/edges/${edgeToEdit.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        type,
                        reason,
                    }),
                });
            }

            setShowEdgeDialog(false);
            setPendingConnection(null);
            setEdgeToEdit(null);
            setUndoCount(prev => prev + 1);
            showSaveStatus();
            loadProject(false);
        } catch (err) {
            console.error('Edge dialog confirm error:', err);
        }
    };

    const handleEdgeClick = (id: string, edge: EdgeData) => {
        if (!isEditMode) return;
        // setEdgeToEdit(edge);
        // setPendingConnection(null);
        // setShowEdgeDialog(true);
        handleEdgeSelect(id);
    };

    const handleEdgeDoubleClick = (id: string, edge: EdgeData) => {
        if (!isEditMode) return;
        setEdgeToEdit(edge);
        setPendingConnection(null);
        setShowEdgeDialog(true);
    };

    const handleEdgesDelete = async (edgeIds: string[]) => {
        if (edgeIds.length === 0) return;
        try {
            await Promise.all(edgeIds.map(id =>
                authFetch(`/api/mindmap/projects/${projectId}/edges/${id}`, {
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
        // ... (existing code handles project reload)
    };

    const handleAutoLayout = useCallback(async (direction = 'LR') => {
        if (!project) return;
        markDirty();

        const dagreGraph = new dagre.graphlib.Graph();
        dagreGraph.setDefaultEdgeLabel(() => ({}));

        const nodeWidth = 240;
        const nodeHeight = 160;

        dagreGraph.setGraph({
            rankdir: direction,
            marginx: 50,
            marginy: 50,
            ranksep: 100,
            nodesep: 80
        });

        activeNodes.forEach((node) => {
            dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
        });

        activeEdges.forEach((edge) => {
            dagreGraph.setEdge(edge.source, edge.target);
        });

        dagre.layout(dagreGraph);

        const newNodes = activeNodes.map((node) => {
            const nodeWithPosition = dagreGraph.node(node.id);
            return {
                ...node,
                position: {
                    x: nodeWithPosition.x - nodeWidth / 2,
                    y: nodeWithPosition.y - nodeHeight / 2,
                },
            };
        });

        // Update local state for immediate feedback
        setProject(prev => prev ? { ...prev, nodes: newNodes } : null);

        // Persist to backend
        try {
            await Promise.all(newNodes.map(node =>
                authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${node.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pos_x: node.position.x, pos_y: node.position.y }),
                })
            ));
            showSaveStatus();
            setUndoCount(prev => prev + 1);
        } catch (err) {
            console.error('Auto layout save error:', err);
            showSaveStatus(true);
            loadProject(false);
        }
    }, [activeNodes, activeEdges, project, projectId, markDirty, showSaveStatus, loadProject]);

    // AI Copilot Handler
    const handleAiAction = async (action: 'summarize' | 'expand' | 'rag' | 'investigate', nodeId: string, content: string) => {
        const node = activeNodes.find(n => n.id === nodeId);
        if (!node) return;

        const actionLabels: Record<string, string> = {
            summarize: `「${node.label}」を要約してください`,
            expand: `「${node.label}」のサブタスクを展開してください`,
            rag: `「${node.label}」に関連する知識を検索してください`,
            investigate: `「${node.label}」について詳しく調べてください`,
        };

        const userMsg = { role: 'user' as const, content: actionLabels[action] || 'AIアクションを実行' };
        setProject(prev => {
            if (!prev) return null;
            return {
                ...prev,
                nodes: prev.nodes.map(n =>
                    n.id === nodeId ? { ...n, chatHistory: [...(n.chatHistory || []), userMsg] } : n
                ),
            };
        });

        showSaveStatus();
        setIsSidebarOpen(true);
        setForceChatTab(nodeId);

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
            let aiContent = data.text || '';

            if ((action === 'expand' || action === 'investigate') && data.children) {
                aiContent += `\n\n**展開候補:**\n${data.children.map((c: any) => `- **${c.label}** (${c.phase} / ${c.category})`).join('\n')}`;
            }

            const aiMsg = { role: 'assistant' as const, content: aiContent || '回答を取得できませんでした' };
            setProject(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    nodes: prev.nodes.map(n =>
                        n.id === nodeId ? { ...n, chatHistory: [...(n.chatHistory || []), aiMsg] } : n
                    ),
                };
            });
        } catch (err) {
            console.error('AI Action error:', err);
            const errMsg = { role: 'assistant' as const, content: 'AI処理に失敗しました。設定を確認してください。' };
            setProject(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    nodes: prev.nodes.map(n =>
                        n.id === nodeId ? { ...n, chatHistory: [...(n.chatHistory || []), errMsg] } : n
                    ),
                };
            });
        }
    };

    const handleChecklistToggle = async (nodeId: string, index: number, checked: boolean) => {
        const node = activeNodes.find(n => n.id === nodeId);
        if (!node) return;

        const currentNotes = (() => {
            try { return JSON.parse((node as any).notes || '{}'); } catch { return {}; }
        })();
        const checkedIndices: number[] = currentNotes.checkedIndices || [];
        const updated = checked
            ? [...new Set([...checkedIndices, index])]
            : checkedIndices.filter(i => i !== index);

        const updates = { notes: JSON.stringify({ ...currentNotes, checkedIndices: updated }) };

        // Optimistic update
        setProject(prev => {
            if (!prev) return null;
            return {
                ...prev,
                nodes: prev.nodes.map(n => n.id === nodeId ? { ...n, ...updates } : n)
            };
        });

        try {
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/nodes/${nodeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });
            showSaveStatus();
        } catch (err) {
            console.error('Checklist toggle error:', err);
            loadProject(false);
        }
    };

    const handleShowCriticalPath = async () => {
        if (selectedNodeIds.size !== 2) return;
        const [fromId, toId] = Array.from(selectedNodeIds);
        try {
            const res = await authFetch(
                `/api/mindmap/path/${project?.template_id}/${fromId}/${toId}`
            );
            if (!res.ok) throw new Error('Critical path failed');
            const data = await res.json();
            if (data.path && data.path.length > 0) {
                setHighlightedNodes(new Set(data.path));
                const pathEdges = activeEdges.filter(e =>
                    data.path.includes(e.source) && data.path.includes(e.target)
                );
                setHighlightedEdges(new Set(pathEdges.map(e => e.id)));
            } else {
                alert('パスが見つかりませんでした');
            }
        } catch (err) {
            console.error('Critical path error:', err);
        }
    };


    const selectedNodeEdges = useMemo(() => {
        if (!selectedNodeId) return { incoming: [] as EdgeData[], outgoing: [] as EdgeData[] };
        const incoming = activeEdges.filter(e => e.target === selectedNodeId);
        const outgoing = activeEdges.filter(e => e.source === selectedNodeId);
        return { incoming, outgoing };
    }, [activeEdges, selectedNodeId]);

    // Consolidated Keyboard Shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            const isInput = document.activeElement instanceof HTMLInputElement ||
                document.activeElement instanceof HTMLTextAreaElement;
            if (isInput) {
                if (e.key === 'Escape') {
                    (document.activeElement as HTMLElement).blur();
                }
                return;
            }

            if (e.key === 'Escape') {
                setSelectedNodeId(null);
                setSelectedNodeIds(new Set());
                setSelectedEdgeId(null);
                setContextMenu(null);
                // フォーカスを外す（検索バー等）
                if (document.activeElement instanceof HTMLElement) {
                    document.activeElement.blur();
                }
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (searchResults.length > 0) {
                    handleSearchNavigation(e.shiftKey ? 'prev' : 'next');
                } else if (selectedNodeId) {
                    // Sibling node creation
                    const node = activeNodes.find(n => n.id === selectedNodeId);
                    if (node) {
                        const incomingEdge = activeEdges.find(ed => ed.target === selectedNodeId);
                        const parentId = incomingEdge?.source;
                        handleAddNodeAt('新規ノード', node.position.x, node.position.y + 120, parentId);
                    }
                }
            } else if (e.key === 'Tab') {
                if (selectedNodeId) {
                    e.preventDefault();
                    const node = activeNodes.find(n => n.id === selectedNodeId);
                    if (node) {
                        handleAddNodeAt('新規ノード', node.position.x + 280, node.position.y, selectedNodeId);
                    }
                }
            } else if ((e.metaKey || e.ctrlKey) && e.key === 'a') {
                e.preventDefault();
                setSelectedNodeIds(new Set(activeNodes.map(n => n.id)));
                setSelectedNodeId(null);
            } else if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
                e.preventDefault();
                handleUndo();
            } else if ((e.metaKey || e.ctrlKey) && e.key === 's') {
                e.preventDefault();
                showSaveStatus();
            } else if (e.key === 'f' || e.key === 'F' || e.key === 'F2') {
                e.preventDefault();
                if (selectedNodeIds.size === 1) {
                    const nodeId = Array.from(selectedNodeIds)[0];
                    setEditingNodeId(nodeId);
                }
                return;
            } else if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'f')) {
                e.preventDefault();
                const searchInput = document.getElementById('goal-search-input') as HTMLInputElement;
                if (searchInput) {
                    searchInput.focus();
                    searchInput.select();
                }
            } else if (e.key === '0') {
                e.preventDefault();
                if (rfInstance) rfInstance.fitView({ duration: 800 });
            } else if (e.key === 'F' && e.shiftKey) {
                e.preventDefault();
                if (rfInstance) rfInstance.fitView({ duration: 800 });
            } else if (e.key === '?' || e.key === 'h') {
                e.preventDefault();
                setShowShortcutsModal(true);
            } else if (!e.shiftKey && (e.key === 'f' || e.key === 'F' || e.key === 'F2')) {
                if (selectedNodeId) {
                    const node = activeNodes.find(n => n.id === selectedNodeId);
                    if (node) {
                        e.preventDefault();
                        setNodeToEdit(node);
                        setShowEditDialog(true);
                    }
                }
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
            } else if (e.key === 'Delete' || e.key === 'Backspace') {
                if (selectedNodeId || selectedNodeIds.size > 0) {
                    e.preventDefault();
                    handleDeleteNode();
                } else if (selectedEdgeId) {
                    e.preventDefault();
                    handleEdgesDelete([selectedEdgeId]);
                }
            } else if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
                e.preventDefault();
                setIsSidebarOpen(prev => !prev);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedNodeId, selectedNodeIds, selectedEdgeId, undoCount, activeNodes, activeEdges, rfInstance, handleUndo, handleAddNodeAt, handleDeleteNode, handleEdgesDelete, handleSearchNavigation, showSaveStatus]);

    // T12: Auto Layout Logic

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

    const handlePaneClick = useCallback(() => {
        setSelectedNodeId(null);
        setSelectedNodeIds(new Set());
        setSelectedEdgeId(null);
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
                        {selectedNodeIds.size === 2 && (
                            <button
                                onClick={handleShowCriticalPath}
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-100 transition-colors shadow-sm"
                            >
                                <GitBranch className="w-3.5 h-3.5" />
                                クリティカルパスを表示
                            </button>
                        )}
                        <button
                            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                            className={`p-2 rounded-md transition-colors ${isSidebarOpen ? 'bg-violet-100 text-violet-600' : 'text-gray-500 hover:bg-gray-100'
                                }`}
                            title="サイドバー切り替え"
                        >
                            <Sidebar className="w-5 h-5" />
                        </button>
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
                    <div className="p-4 border-b border-[var(--border)] overflow-y-auto max-h-[40vh]">
                        <h4 className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider mb-2 flex items-center gap-2">
                            <span>🎯 次の決定事項</span>
                            <span className="text-[10px] bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded-full border border-amber-100 italic font-normal">
                                {nextActions.length} items
                            </span>
                        </h4>
                        <div className="space-y-1">
                            {nextActions.map(action => (
                                <button
                                    key={action.node_id}
                                    onClick={() => setSelectedNodeId(action.node_id)}
                                    className="w-full text-left px-2 py-2 text-xs rounded-lg hover:bg-[var(--background)] transition-colors border border-transparent hover:border-[var(--border)] active:scale-[0.98]"
                                >
                                    <span className="text-[var(--foreground)] font-medium block leading-tight mb-1">{action.label}</span>
                                    <div className="flex items-center gap-2 text-[var(--muted)] text-[9px]">
                                        <span className="bg-slate-100 px-1 py-0.5 rounded">{action.phase}</span>
                                        <span className="flex items-center gap-1">
                                            <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[action.category] || '#ccc' }} />
                                            {action.category}
                                        </span>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="p-4 border-b border-[var(--border)]">
                        <GoalSearchBar
                            nodes={activeNodes}
                            onSearch={(nodeId) => {
                                handleGoalSearch(nodeId);
                                jumpToNode(nodeId);
                            }}
                            onClear={clearHighlight}
                            highlightedCount={highlightedNodes.size}
                            templateId={project?.template_id || ''}
                            onReverseTreeResult={(nodeIds, edgeIds) => {
                                setHighlightedNodes(new Set(nodeIds));
                                setHighlightedEdges(new Set(edgeIds));
                                setSearchResults(nodeIds);
                                setCurrentSearchIndex(0);
                                if (nodeIds.length > 0) jumpToNode(nodeIds[0]);
                            }}
                            currentResultIndex={currentSearchIndex}
                            totalResults={searchResults.length}
                            onNavigateResult={handleSearchNavigation}
                        />
                    </div>

                    <div className="p-4">
                        <FilterPanel
                            phases={PHASES}
                            categories={CATEGORIES}
                            selectedPhases={filterPhases}
                            selectedCategories={filterCategories}
                            onTogglePhase={togglePhase}
                            onToggleCategory={toggleCategory}
                            onClearAll={() => {
                                setFilterPhases(new Set());
                                setFilterCategories(new Set());
                            }}
                            categoryColors={CATEGORY_COLORS}
                        />
                    </div>
                </aside>

                <main className="flex-1 overflow-hidden relative bg-white min-w-[320px]"
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
                            selectedEdgeId={selectedEdgeId}
                            pulsingNodeId={pulsingNodeId}
                            highlightedNodes={highlightedNodes}
                            highlightedEdges={highlightedEdges}
                            onNodeSelect={setSelectedNodeId}
                            onSelectionChange={handleSelectionChange}
                            categoryColors={CATEGORY_COLORS}
                            isEditMode={isEditMode}
                            onNodeDragStop={handleNodeDragStop}
                            onAddNodeAt={handleAddNodeAt}
                            onConnectNodes={handleConnectNodes}
                            onEdgeUpdate={handleEdgeUpdate}
                            onEdgeClick={handleEdgeClick}
                            onEdgeDoubleClick={handleEdgeDoubleClick}
                            onEdgeContextMenu={(e, edge) => {
                                setContextMenu({ x: e.clientX, y: e.clientY, type: 'edge', targetId: edge.id });
                                setEdgeToEdit(edge);
                            }}
                            onEdgesDelete={handleEdgesDelete}
                            onNodesDelete={handleNodesDelete}
                            collapsedNodeIds={collapsedNodeIds}
                            descendantCounts={descendantCounts}
                            onNodeLabelChange={handleNodeLabelChange}
                            onNodeCollapse={handleNodeCollapse}
                            onNodeContextMenu={handleNodeContextMenu}
                            onPaneContextMenu={handlePaneContextMenu}
                            onPaneClick={handlePaneClick}
                            onAiAction={handleAiAction}
                            editingNodeId={editingNodeId}
                            onClearEditingNode={() => setEditingNodeId(null)}
                        />
                        <div className="absolute top-4 right-4 flex flex-col gap-2">
                            <EditToolbar
                                isEditMode={isEditMode}
                                isProjectMode={true}
                                onToggleEditMode={() => setIsEditMode(!isEditMode)}
                                onAddNode={() => setShowAddDialog(true)}
                                onDeleteNode={handleDeleteNode}
                                onGapCheck={() => setShowGapAdvisorModal(true)}
                                onInvestigate={() => {
                                    if (selectedNodeId) return handleAiAction('investigate', selectedNodeId, '');
                                    if (selectedNodeIds.size > 0) return handleAiAction('investigate', Array.from(selectedNodeIds)[0], '');
                                    return null;
                                }}
                                onUndo={handleUndo}
                                onBatchStatusChange={handleBatchStatusChange}
                                onLayout={handleAutoLayout}
                                hasSelectedNode={!!selectedNodeId || selectedNodeIds.size > 0}
                                selectedCount={selectedNodeIds.size > 0 ? selectedNodeIds.size : (selectedNodeId ? 1 : 0)}
                                canUndo={undoCount > 0}
                            />
                        </div>
                    </ReactFlowProvider>
                </main>

                {isSidebarOpen && (
                    <aside
                        className="border-l border-[var(--border)] bg-white/50 flex flex-col shadow-xl z-20 relative flex-shrink-0 transition-all duration-300"
                        style={{ width: isSidebarMaximized ? 'min(800px, 90vw)' : sidebarWidth }}
                    >
                        {/* Resizer Handle */}
                        {!isSidebarMaximized && (
                            <div
                                className="absolute left-0 top-0 bottom-0 w-3 cursor-ew-resize hover:bg-violet-400/20 z-50 flex items-center justify-center group -ml-1.5"
                                onMouseDown={startSidebarResize}
                            >
                                <div className="w-1 h-12 bg-gray-300 rounded-full group-hover:bg-violet-500 transition-colors" />
                            </div>
                        )}

                        <div className="flex-1 w-full overflow-hidden flex flex-col">
                            {/* Panel Controls */}
                            <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--border)] bg-white/80">
                                <span className="text-[10px] font-bold text-[var(--muted)] uppercase tracking-wider">詳細パネル</span>
                                <div className="flex items-center gap-1">
                                    <button
                                        onClick={() => setIsSidebarMaximized(!isSidebarMaximized)}
                                        className="p-1 rounded text-[var(--muted)] hover:text-violet-600 hover:bg-violet-50 transition-colors"
                                        title={isSidebarMaximized ? 'パネルを縮小' : 'パネルを最大化'}
                                    >
                                        {isSidebarMaximized ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                                    </button>
                                    <button
                                        onClick={() => setIsSidebarOpen(false)}
                                        className="p-1 rounded text-[var(--muted)] hover:text-red-600 hover:bg-red-50 transition-colors"
                                        title="パネルを閉じる"
                                    >
                                        <X className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                            </div>

                            <IntegratedSidebar
                                selectedNode={selectedNode}
                                knowledge={selectedNode?.ragResults || []}
                                chatHistory={selectedNode?.chatHistory || []}
                                isSearching={isSearching}
                                onChatSend={handleChatSend}
                                onDragStart={onDragStartKnowledge}
                                incomingEdges={selectedNodeEdges.incoming}
                                outgoingEdges={selectedNodeEdges.outgoing}
                                getNodeLabel={(id) => activeNodes.find(n => n.id === id)?.label || id}
                                onNavigate={setSelectedNodeId}
                                isEditMode={isEditMode}
                                onStatusChange={handleStatusChange}
                                onUpdate={handleNodeUpdate}
                                onChecklistToggle={handleChecklistToggle}
                                categoryColors={CATEGORY_COLORS}
                                phases={PHASES}
                                categories={CATEGORIES}
                                forceChatTab={forceChatTab === selectedNode?.id}
                                onSendToMap={handleSendToMap}
                                projectId={projectId}
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

            {showEditDialog && nodeToEdit && (
                <EditNodeDialog
                    node={nodeToEdit}
                    onClose={() => {
                        setShowEditDialog(false);
                        setNodeToEdit(null);
                    }}
                    onSave={handleNodeUpdate}
                />
            )}

            {showEdgeDialog && (
                <EditEdgeDialog
                    isOpen={showEdgeDialog}
                    onClose={() => {
                        setShowEdgeDialog(false);
                        setPendingConnection(null);
                        setEdgeToEdit(null);
                    }}
                    onSave={handleEdgeDialogConfirm}
                    initialType={edgeToEdit?.type as 'hard' | 'soft' || 'hard'}
                    initialReason={edgeToEdit?.reason || ''}
                    title={edgeToEdit ? '依存関係の編集' : '新しい依存関係'}
                />
            )}

            {showGapAdvisorModal && project && (
                <GapAdvisorModal
                    isOpen={showGapAdvisorModal}
                    onClose={() => setShowGapAdvisorModal(false)}
                    projectId={projectId}
                    initialContext={{
                        technical_conditions: project.technical_conditions || '',
                        legal_requirements: project.legal_requirements || ''
                    }}
                    onApplySuggestions={() => loadProject(false)}
                />
            )}

            <SaveStatusOverlay
                status={saveStatus}
                lastSavedAt={lastSavedAt}
                onRetry={() => {
                    setSaveStatus('saving');
                    loadProject(false);
                }}
            />

            <KeyboardShortcutsModal 
                isOpen={showShortcutsModal} 
                onClose={() => setShowShortcutsModal(false)} 
            />

            <MobileMindmapControls
                nodes={activeNodes}
                nextActions={nextActions}
                phases={PHASES}
                categories={CATEGORIES}
                selectedPhases={filterPhases}
                selectedCategories={filterCategories}
                onTogglePhase={togglePhase}
                onToggleCategory={toggleCategory}
                onClearFilters={() => {
                    setFilterPhases(new Set());
                    setFilterCategories(new Set());
                }}
                categoryColors={CATEGORY_COLORS}
                templateId={project?.template_id || ''}
                highlightedCount={highlightedNodes.size}
                onReverseTreeResult={(nodeIds, edgeIds) => {
                    setHighlightedNodes(new Set(nodeIds));
                    setHighlightedEdges(new Set(edgeIds));
                }}
                onNodeSelect={setSelectedNodeId}
                onClearSearch={clearHighlight}
            />

            {contextMenu && (
                <ContextMenu
                    x={contextMenu.x}
                    y={contextMenu.y}
                    options={[
                        ...(contextMenu.type === 'node' || contextMenu.type === 'edge' ? [
                            {
                                label: edgeToEdit ? 'エッジ編集' : '編集',
                                icon: <Edit2 className="w-4 h-4" />,
                                action: () => {
                                    if (edgeToEdit) {
                                        setShowEdgeDialog(true);
                                    } else if (contextMenu.targetId) {
                                        const node = activeNodes.find(n => n.id === contextMenu.targetId);
                                        if (node) {
                                            setNodeToEdit(node);
                                            setShowEditDialog(true);
                                        }
                                    }
                                    handleCloseContextMenu();
                                }
                            },
                            {
                                label: '削除',
                                icon: <Trash2 className="w-4 h-4 text-red-500" />,
                                action: () => {
                                    if (edgeToEdit) {
                                        handleEdgesDelete([edgeToEdit.id]);
                                        setEdgeToEdit(null);
                                    } else if (contextMenu.targetId) {
                                        handleNodesDelete([contextMenu.targetId]);
                                    }
                                    handleCloseContextMenu();
                                }
                            },
                        ] : []),
                        ...(contextMenu.type === 'pane' ? [
                            {
                                label: 'ノードを追加',
                                icon: <Plus className="w-4 h-4" />,
                                action: () => {
                                    setShowAddDialog(true);
                                    handleCloseContextMenu();
                                }
                            }
                        ] : [])
                    ]}
                    onClose={() => {
                        setContextMenu(null);
                        // Only clear edgeToEdit if we are not opening the dialog
                    }}
                />
            )}
        </div>
    );
}
