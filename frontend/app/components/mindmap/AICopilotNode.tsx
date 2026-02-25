'use client';

import { memo, useRef, useState, useEffect } from 'react';
import { Handle, Position, NodeProps, NodeToolbar } from 'reactflow';
import { CheckSquare, Check, Clock, Minus, ChevronDown, ChevronRight, FileText, Lightbulb, Search, Sparkles } from 'lucide-react';

interface CustomNodeData {
    label: string;
    phase: string;
    category: string;
    status: string;
    checklistCount: number;
    color: string;
    isSelected: boolean;
    isHighlighted: boolean;
    isDimmed: boolean;
    collapsed: boolean;
    hasChildren: boolean;
    hiddenDescendantCount?: number;
    onLabelChange?: (newLabel: string) => void;
    onCollapseToggle?: () => void;
    onContextMenu?: (e: React.MouseEvent) => void;
    // AI Action handlers
    onAiAction?: (action: 'summarize' | 'expand' | 'rag', nodeId: string, label: string) => void;
}

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; bg: string; text: string }> = {
    '決定済み': {
        icon: <Check className="w-3 h-3" />,
        bg: '#dcfce7',
        text: '#16a34a',
    },
    '検討中': {
        icon: <Clock className="w-3 h-3" />,
        bg: '#fef3c7',
        text: '#d97706',
    },
    '未着手': {
        icon: <Minus className="w-3 h-3" />,
        bg: '#f1f5f9',
        text: '#94a3b8',
    },
};

function AICopilotNode({ data, id, selected }: NodeProps<CustomNodeData>) {
    const status = STATUS_CONFIG[data.status] || STATUS_CONFIG['未着手'];
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(data.label);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        if (isEditing && inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
            inputRef.current.style.height = 'auto';
            inputRef.current.style.height = inputRef.current.scrollHeight + 'px';
        }
    }, [isEditing]);

    const handleDoubleClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        setIsEditing(true);
        setEditValue(data.label);
    };

    const handleBlur = () => {
        setIsEditing(false);
        if (editValue.trim() !== data.label && data.onLabelChange) {
            data.onLabelChange(editValue.trim());
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleBlur();
        }
        if (e.key === 'Escape') {
            setIsEditing(false);
            setEditValue(data.label);
        }
    };

    const handleCollapseClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        if (data.onCollapseToggle) {
            data.onCollapseToggle();
        }
    };

    const handleAiAction = (action: 'summarize' | 'expand' | 'rag') => {
        if (data.onAiAction) {
            data.onAiAction(action, id, data.label);
        }
    };

    return (
        <>
            <NodeToolbar isVisible={selected} position={Position.Top} className="flex gap-1 p-1 bg-white rounded-lg border border-slate-200 shadow-xl">
                <button
                    onClick={() => handleAiAction('summarize')}
                    className="flex items-center gap-1.5 px-2 py-1.5 text-xs font-medium text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                    title="要約 (Summarize)"
                >
                    <FileText className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">要約</span>
                </button>
                <div className="w-px bg-slate-200 my-1" />
                <button
                    onClick={() => handleAiAction('expand')}
                    className="flex items-center gap-1.5 px-2 py-1.5 text-xs font-medium text-slate-600 hover:text-violet-600 hover:bg-violet-50 rounded transition-colors"
                    title="拡張 (Expand)"
                >
                    <Lightbulb className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">拡張</span>
                </button>
                <div className="w-px bg-slate-200 my-1" />
                <button
                    onClick={() => handleAiAction('rag')}
                    className="flex items-center gap-1.5 px-2 py-1.5 text-xs font-medium text-slate-600 hover:text-emerald-600 hover:bg-emerald-50 rounded transition-colors"
                    title="補完 (RAG Check)"
                >
                    <Search className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">RAG</span>
                </button>
            </NodeToolbar>

            <Handle
                type="target"
                position={Position.Left}
                className="!w-2.5 !h-2.5 !bg-white !border-2 !border-slate-300 hover:!border-blue-500 !transition-colors"
            />

            <div
                className={`
                    group relative
                    rounded-lg bg-white min-w-[160px] max-w-[220px]
                    transition-all duration-200 cursor-pointer
                    ${selected
                        ? 'ring-2 ring-violet-500 ring-offset-2 ring-offset-[var(--canvas-bg)] scale-105 shadow-lg'
                        : ''
                    }
                    ${data.isDimmed
                        ? 'opacity-20 scale-95'
                        : 'hover:shadow-md'
                    }
                `}
                style={{
                    boxShadow: data.isDimmed
                        ? 'none'
                        : selected
                            ? `0 4px 12px rgba(0,0,0,0.1), 0 0 0 1px ${data.color}30`
                            : '0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)',
                    borderLeft: `4px solid ${data.isDimmed ? '#cbd5e1' : data.color}`,
                }}
                onDoubleClick={handleDoubleClick}
                onContextMenu={data.onContextMenu}
            >
                {/* AI Badge for visual flair */}
                <div className="absolute -top-2 right-4 bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white p-1 rounded-full shadow-sm opacity-0 group-hover:opacity-100 transition-opacity z-10">
                    <Sparkles className="w-3 h-3" />
                </div>

                {/* Collapse Toggle */}
                {data.hasChildren && data.onCollapseToggle && (
                    <button
                        onClick={handleCollapseClick}
                        className={`absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 bg-white border rounded-full flex items-center justify-center shadow-sm hover:bg-slate-50 transition-colors z-10 ${data.collapsed
                            ? 'text-blue-600 border-blue-300 bg-blue-50'
                            : 'text-slate-500 border-slate-200'
                            }`}
                    >
                        {data.collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                )}

                <div className="px-3 py-2.5">
                    {/* Phase badge */}
                    <div
                        className="text-[9px] font-semibold uppercase tracking-wider mb-1.5 px-1.5 py-0.5 rounded inline-block"
                        style={{
                            backgroundColor: data.isDimmed ? '#f1f5f9' : `${data.color}15`,
                            color: data.isDimmed ? '#cbd5e1' : data.color,
                        }}
                    >
                        {data.phase}
                    </div>

                    {/* Label Area */}
                    <div className="mb-2 min-h-[1.25rem]">
                        {isEditing ? (
                            <textarea
                                ref={inputRef}
                                value={editValue}
                                onChange={(e) => {
                                    setEditValue(e.target.value);
                                    e.target.style.height = 'auto';
                                    e.target.style.height = e.target.scrollHeight + 'px';
                                }}
                                onBlur={handleBlur}
                                onKeyDown={handleKeyDown}
                                className="w-full text-sm font-bold leading-tight bg-blue-50 px-1 py-0.5 rounded outline-none resize-none overflow-hidden"
                                style={{ color: '#1e293b' }}
                                onClick={(e) => e.stopPropagation()}
                            />
                        ) : (
                            <div
                                className="text-sm font-bold leading-tight break-words select-none"
                                style={{
                                    color: data.isDimmed ? '#cbd5e1' : '#1e293b',
                                }}
                            >
                                {data.label}
                                {data.collapsed && (data.hiddenDescendantCount || 0) > 0 && (
                                    <span className="ml-1.5 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 border border-blue-200 align-middle">
                                        +{data.hiddenDescendantCount}
                                    </span>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between">
                        <span
                            className="flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                            style={{
                                backgroundColor: data.isDimmed ? '#f8fafc' : status.bg,
                                color: data.isDimmed ? '#cbd5e1' : status.text,
                            }}
                        >
                            {status.icon}
                            {data.status}
                        </span>
                        {data.checklistCount > 0 && (
                            <span
                                className="flex items-center gap-0.5 text-[10px]"
                                style={{ color: data.isDimmed ? '#cbd5e1' : '#94a3b8' }}
                            >
                                <CheckSquare className="w-3 h-3" />
                                {data.checklistCount}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            <Handle
                type="source"
                position={Position.Right}
                className={`!w-2.5 !h-2.5 !bg-white !border-2 !border-slate-300 hover:!border-blue-500 !transition-colors ${data.collapsed ? '!opacity-0 !pointer-events-none' : ''}`}
            />
        </>
    );
}

export default memo(AICopilotNode);
