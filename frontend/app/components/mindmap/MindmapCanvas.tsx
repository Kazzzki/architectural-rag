'use client';

import { useMemo, useCallback, useEffect, useState, useRef } from 'react';
import ReactFlow, {
    Node,
    Edge as RFEdge,
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    BackgroundVariant,
    MarkerType,
    NodeMouseHandler,
    NodeDragHandler,
    Connection,
    OnConnectEnd,
    useReactFlow,
    OnSelectionChangeFunc,
    SelectionMode,
} from 'reactflow';
import 'reactflow/dist/style.css';
import CustomNode from './CustomNode';
import AICopilotNode from './AICopilotNode';

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
}

interface EdgeData {
    id: string;
    source: string;
    target: string;
    type: string;
    reason: string;
}

interface Props {
    nodes: ProcessNode[];
    edges: EdgeData[];
    selectedNodeId: string | null;
    selectedNodeIds?: Set<string>;
    highlightedNodes: Set<string>;
    highlightedEdges: Set<string>;
    onNodeSelect: (id: string) => void;
    onSelectionChange?: (nodeIds: string[]) => void;
    categoryColors: Record<string, string>;
    isEditMode?: boolean;
    onNodeDragStop?: (nodeId: string, x: number, y: number) => void;
    onAddNodeAt?: (label: string, x: number, y: number, sourceNodeId?: string) => void;
    onConnectNodes?: (sourceId: string, targetId: string) => void;
    onEdgeUpdate?: (oldEdge: EdgeData, newConnection: Connection) => void;
    onEdgesDelete?: (edgeIds: string[]) => void;
    onNodesDelete?: (nodeIds: string[]) => void;
    collapsedNodeIds?: Set<string>;
    descendantCounts?: Map<string, number>;
    onNodeLabelChange?: (nodeId: string, newLabel: string) => void;
    onNodeCollapse?: (nodeId: string) => void;
    onNodeContextMenu?: (event: React.MouseEvent, nodeId: string) => void;
    onPaneContextMenu?: (event: React.MouseEvent) => void;
    onAiAction?: (action: 'summarize' | 'expand' | 'rag', nodeId: string, label: string) => void;
    allEdges?: EdgeData[];
}

const nodeTypes = { custom: CustomNode, aiCopilot: AICopilotNode };
const EMPTY_SET = new Set<string>();
const EMPTY_MAP = new Map<string, number>();

function MindmapCanvasInner({
    nodes: processNodes,
    edges: processEdges,
    allEdges,
    selectedNodeId,
    selectedNodeIds = EMPTY_SET,
    highlightedNodes,
    highlightedEdges,
    onNodeSelect,
    onSelectionChange,
    categoryColors,
    isEditMode = false,
    onNodeDragStop,
    onAddNodeAt,
    onConnectNodes,
    onEdgeUpdate,
    onEdgesDelete,
    onNodesDelete,
    collapsedNodeIds = EMPTY_SET,
    descendantCounts = EMPTY_MAP,
    onNodeLabelChange,
    onNodeCollapse,
    onNodeContextMenu,
    onPaneContextMenu,
    onAiAction,
}: Props) {
    const hasHighlight = highlightedNodes.size > 0;
    const { screenToFlowPosition } = useReactFlow();

    // Inline input state
    const [inlineInput, setInlineInput] = useState<{
        x: number;
        y: number;
        flowX: number;
        flowY: number;
        sourceNodeId?: string;
    } | null>(null);
    const [inlineValue, setInlineValue] = useState('');
    const inlineRef = useRef<HTMLInputElement>(null);
    const connectingNodeId = useRef<string | null>(null);

    // Focus inline input when shown
    useEffect(() => {
        if (inlineInput && inlineRef.current) {
            inlineRef.current.focus();
        }
    }, [inlineInput]);

    // Build set of node IDs that have children (for collapse button visibility)
    const nodeIdsWithChildren = useMemo(() => {
        const parentIds = new Set<string>();
        if (allEdges) {
            allEdges.forEach(e => parentIds.add(e.source));
        } else {
            processEdges.forEach(e => parentIds.add(e.source));
        }
        return parentIds;
    }, [processEdges, allEdges]);

    const isDraggingRef = useRef(false);

    // Convert to React Flow nodes
    const nodeFingerprint = processNodes
        .map(n => `${n.id}:${n.status}:${n.label}:${Math.round(n.position.x)}:${Math.round(n.position.y)}`)
        .join('|');

    const rfNodes: Node[] = useMemo(() => {
        return processNodes.map(pn => ({
            id: pn.id,
            // Use 'aiCopilot' type to enable AI features, or fallback to 'custom'
            type: 'aiCopilot',
            position: pn.position,
            selected: pn.id === selectedNodeId,
            data: {
                label: pn.label,
                phase: pn.phase,
                category: pn.category,
                status: pn.status,
                checklistCount: pn.checklist.length,
                color: categoryColors[pn.category] || '#6b7280',
                isSelected: pn.id === selectedNodeId,
                isHighlighted: hasHighlight ? highlightedNodes.has(pn.id) : true,
                isDimmed: hasHighlight && !highlightedNodes.has(pn.id),
                collapsed: collapsedNodeIds.has(pn.id),
                hiddenDescendantCount: descendantCounts.get(pn.id),
                hasChildren: nodeIdsWithChildren.has(pn.id) || collapsedNodeIds.has(pn.id),
                onLabelChange: isEditMode && onNodeLabelChange ? (newLabel: string) => onNodeLabelChange(pn.id, newLabel) : undefined,
                onCollapseToggle: onNodeCollapse && (nodeIdsWithChildren.has(pn.id) || collapsedNodeIds.has(pn.id)) ? () => onNodeCollapse(pn.id) : undefined,
                onContextMenu: onNodeContextMenu ? (e: React.MouseEvent) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onNodeContextMenu(e, pn.id);
                } : undefined,
                onAiAction: onAiAction,
            },
        }));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [nodeFingerprint, selectedNodeId, highlightedNodes, hasHighlight, categoryColors, collapsedNodeIds, descendantCounts, nodeIdsWithChildren, isEditMode, onNodeLabelChange, onNodeCollapse, onNodeContextMenu, onAiAction]);

    // Convert to React Flow edges
    const rfEdges: RFEdge[] = useMemo(() => {
        return processEdges.map(pe => {
            const isHighlighted = hasHighlight ? highlightedEdges.has(pe.id) : true;
            const isDimmed = hasHighlight && !highlightedEdges.has(pe.id);
            const isHard = pe.type === 'hard';

            return {
                id: pe.id,
                source: pe.source,
                target: pe.target,
                type: 'smoothstep',
                animated: isHighlighted && hasHighlight,
                // hard: solid/thick / soft: dashed/thin
                style: {
                    stroke: isDimmed ? '#e2e8f0' : isHighlighted ? '#6366f1' : (isHard ? '#94a3b8' : '#cbd5e1'),
                    strokeWidth: isDimmed ? 1 : (isHard ? 2 : 1.5),
                    strokeDasharray: isHard ? undefined : '6 3',
                    opacity: isDimmed ? 0.3 : 1,
                },
                markerEnd: {
                    type: MarkerType.ArrowClosed,
                    color: isDimmed ? '#e2e8f0' : isHighlighted ? '#6366f1' : (isHard ? '#94a3b8' : '#cbd5e1'),
                    width: isHard ? 12 : 10,
                    height: isHard ? 12 : 10,
                },
                label: isHighlighted && hasHighlight ? pe.reason : undefined,
                labelStyle: {
                    fontSize: 9,
                    fill: '#64748b',
                    fontWeight: 500,
                },
                labelBgStyle: {
                    fill: '#ffffff',
                    fillOpacity: 0.9,
                },
                labelBgPadding: [4, 2] as [number, number],
                labelBgBorderRadius: 4,
            };
        });
    }, [processEdges, highlightedEdges, hasHighlight]);

    const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

    // Sync when input changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        setNodes((nds) => {
            return rfNodes.map((newN) => {
                // If dragging, preserve current position to prevent snap-back
                if (isDraggingRef.current) {
                    const currentN = nds.find((n) => n.id === newN.id);
                    if (currentN) {
                        return {
                            ...newN,
                            position: currentN.position,
                            positionAbsolute: currentN.positionAbsolute,
                        };
                    }
                }
                return newN;
            });
        });
    }, [rfNodes]);

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        setEdges(rfEdges);
    }, [rfEdges]);

    const onNodeClick: NodeMouseHandler = useCallback(
        (_, node) => {
            onNodeSelect(node.id);
        },
        [onNodeSelect]
    );

    const onDragStart: NodeDragHandler = useCallback(() => {
        isDraggingRef.current = true;
    }, []);

    const onDragStop: NodeDragHandler = useCallback(
        (_, node) => {
            isDraggingRef.current = false;
            if (onNodeDragStop) {
                onNodeDragStop(node.id, node.position.x, node.position.y);
            }
        },
        [onNodeDragStop]
    );

    // Multi-select handler — use a ref to debounce and avoid re-render loops
    const selectionChangeRef = useRef(onSelectionChange);
    selectionChangeRef.current = onSelectionChange;

    const handleSelectionChange: OnSelectionChangeFunc = useCallback(
        ({ nodes: selectedNodes }) => {
            if (selectionChangeRef.current) {
                selectionChangeRef.current(selectedNodes.map(n => n.id));
            }
        },
        []
    );

    // Handle drag from handle to existing node → edge connection
    const onConnect = useCallback(
        (connection: Connection) => {
            if (onConnectNodes && connection.source && connection.target) {
                onConnectNodes(connection.source, connection.target);
            }
        },
        [onConnectNodes]
    );

    // Track which node started a connection drag
    const onConnectStart = useCallback(
        (_: any, params: { nodeId: string | null }) => {
            connectingNodeId.current = params.nodeId;
        },
        []
    );

    // Handle drag from handle to empty space → inline input for new node
    const onConnectEnd: OnConnectEnd = useCallback(
        (event: MouseEvent | TouchEvent) => {
            if (!isEditMode || !onAddNodeAt) return;

            const targetIsPane = (event.target as HTMLElement)?.classList?.contains('react-flow__pane');
            if (targetIsPane && connectingNodeId.current) {
                let clientX: number, clientY: number;
                if ('changedTouches' in event) {
                    clientX = event.changedTouches[0].clientX;
                    clientY = event.changedTouches[0].clientY;
                } else {
                    clientX = event.clientX;
                    clientY = event.clientY;
                }

                const flowPos = screenToFlowPosition({ x: clientX, y: clientY });

                setInlineInput({
                    x: clientX,
                    y: clientY,
                    flowX: flowPos.x,
                    flowY: flowPos.y,
                    sourceNodeId: connectingNodeId.current || undefined,
                });
                setInlineValue('');
            }
            connectingNodeId.current = null;
        },
        [isEditMode, onAddNodeAt, screenToFlowPosition]
    );

    // Handle double-click on canvas → inline input for independent node
    const onPaneDoubleClick = useCallback(
        (event: React.MouseEvent) => {
            if (!isEditMode || !onAddNodeAt) return;

            const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });

            setInlineInput({
                x: event.clientX,
                y: event.clientY,
                flowX: flowPos.x,
                flowY: flowPos.y,
            });
            setInlineValue('');
        },
        [isEditMode, onAddNodeAt, screenToFlowPosition]
    );

    // Confirm inline input
    const confirmInlineInput = useCallback(() => {
        if (inlineValue.trim() && onAddNodeAt && inlineInput) {
            onAddNodeAt(
                inlineValue.trim(),
                inlineInput.flowX,
                inlineInput.flowY,
                inlineInput.sourceNodeId
            );
        }
        setInlineInput(null);
        setInlineValue('');
    }, [inlineValue, onAddNodeAt, inlineInput]);

    const cancelInlineInput = useCallback(() => {
        setInlineInput(null);
        setInlineValue('');
    }, []);

    const onNodeContextMenuHandler: NodeMouseHandler = useCallback(
        (event, node) => {
            if (onNodeContextMenu) {
                event.preventDefault();
                onNodeContextMenu(event, node.id);
            }
        },
        [onNodeContextMenu]
    );

    const onPaneContextMenuHandler = useCallback(
        (event: React.MouseEvent) => {
            if (onPaneContextMenu) {
                event.preventDefault();
                onPaneContextMenu(event);
            }
        },
        [onPaneContextMenu]
    );

    return (
        <div style={{ width: '100%', height: '100%', position: 'relative' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onNodeDragStart={onDragStart}
                onNodeDragStop={onDragStop}
                onConnect={onConnect}
                onConnectStart={onConnectStart}
                onConnectEnd={onConnectEnd}
                onEdgeUpdate={onEdgeUpdate ? (oldEdge, newConnection) => {
                    // Convert RF edge back to EdgeData or just pass ID?
                    // ReactFlow passes RFEdge. We need to find corresponding EdgeData or just pass ID.
                    // Actually simpliest is to pass the data needed for parent to handle.
                    const edgeData = processEdges.find(e => e.id === oldEdge.id);
                    if (edgeData) onEdgeUpdate(edgeData, newConnection);
                } : undefined}
                onEdgesDelete={onEdgesDelete ? (edges) => {
                    onEdgesDelete(edges.map(e => e.id));
                } : undefined}
                onNodesDelete={onNodesDelete ? (nodes) => {
                    onNodesDelete(nodes.map(n => n.id));
                } : undefined}
                onContextMenu={onPaneContextMenuHandler}
                onNodeContextMenu={onNodeContextMenuHandler}
                onPaneClick={() => setInlineInput(null)}
                onSelectionChange={handleSelectionChange}
                nodeTypes={nodeTypes}
                defaultViewport={{ x: 50, y: 50, zoom: 0.65 }}
                minZoom={0.2}
                maxZoom={2}
                nodesDraggable={true}
                nodesConnectable={isEditMode}
                selectionOnDrag={false}
                selectionMode={SelectionMode.Partial}
                panOnDrag={true}
                panOnScroll={true}
                multiSelectionKeyCode="Shift"
                proOptions={{ hideAttribution: true }}
            >
                <Background
                    variant={BackgroundVariant.Dots}
                    gap={20}
                    size={1.2}
                    color="var(--canvas-grid)"
                />
                <Controls
                    showInteractive={false}
                />
                <div className="absolute bottom-4 left-4 z-10 flex items-center gap-3 bg-white/80 backdrop-blur-sm rounded-lg px-3 py-1.5 text-[10px] text-slate-500 shadow-sm border border-slate-200">
                    <span className="flex items-center gap-1.5">
                        <span className="inline-block w-4 border-t-2 border-slate-400" />
                        必須依存
                    </span>
                    <span className="flex items-center gap-1.5">
                        <span className="inline-block w-4 border-t-2 border-dashed border-slate-300" />
                        参照依存
                    </span>
                </div>
                <MiniMap
                    nodeColor={(n) => n.data?.color || '#6b7280'}
                    maskColor="rgba(241, 245, 249, 0.7)"
                    pannable
                    zoomable
                />
            </ReactFlow>

            {/* Double-click overlay zone (only in edit mode) */}
            {isEditMode && (
                <div
                    style={{
                        position: 'absolute',
                        inset: 0,
                        zIndex: 1,
                        pointerEvents: 'none',
                    }}
                    onDoubleClick={onPaneDoubleClick}
                />
            )}

            {/* Inline node input */}
            {inlineInput && (
                <div
                    className="inline-node-input"
                    style={{
                        position: 'fixed',
                        left: inlineInput.x,
                        top: inlineInput.y,
                        transform: 'translate(-50%, -50%)',
                        zIndex: 1000,
                    }}
                >
                    <div className="bg-white rounded-lg shadow-xl border border-blue-300 overflow-hidden"
                        style={{ minWidth: 200 }}
                    >
                        <div className="px-3 py-1.5 bg-blue-50 border-b border-blue-200 text-[10px] font-medium text-blue-600 flex items-center gap-1">
                            {inlineInput.sourceNodeId ? '🔗 接続先ノードを作成' : '📌 新規ノード作成'}
                        </div>
                        <input
                            ref={inlineRef}
                            type="text"
                            value={inlineValue}
                            onChange={(e) => setInlineValue(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    confirmInlineInput();
                                } else if (e.key === 'Escape') {
                                    cancelInlineInput();
                                }
                            }}
                            onBlur={cancelInlineInput}
                            placeholder="ノード名を入力..."
                            className="w-full px-3 py-2 text-sm text-gray-800 bg-white border-0 outline-none placeholder:text-gray-400"
                        />
                        <div className="px-3 py-1 bg-gray-50 text-[9px] text-gray-400 border-t">
                            Enter 確定 · Esc キャンセル
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// Wrapper to ensure useReactFlow is usable (needs ReactFlowProvider parent)
export default function MindmapCanvas(props: Props) {
    return <MindmapCanvasInner {...props} />;
}
