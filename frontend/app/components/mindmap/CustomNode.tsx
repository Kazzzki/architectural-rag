'use client';

import { memo, useRef, useState, useEffect } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { CheckSquare, Check, Clock, Minus, ChevronDown, ChevronRight } from 'lucide-react';

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

function CustomNode({ data, id }: NodeProps<CustomNodeData>) {
    const status = STATUS_CONFIG[data.status] || STATUS_CONFIG['未着手'];
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(data.label);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        if (isEditing && inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
            // Adjust height
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

    return (
        <>
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
                    ${data.isSelected
                        ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-[var(--canvas-bg)] scale-105'
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
                        : data.isSelected
                            ? `0 4px 12px rgba(0,0,0,0.1), 0 0 0 1px ${data.color}30`
                            : '0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)',
                    borderLeft: `4px solid ${data.isDimmed ? '#cbd5e1' : data.color}`,
                }}
                onDoubleClick={handleDoubleClick}
                onContextMenu={data.onContextMenu}
            >
                {/* Collapse Toggle (Right Edge) - only for nodes with children */}
                {data.hasChildren && data.onCollapseToggle && (
                    <button
                        onClick={handleCollapseClick}
                        className={`absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 bg-white border rounded-full flex items-center justify-center shadow-sm hover:bg-slate-50 transition-colors z-10 ${data.collapsed
                                ? 'text-blue-600 border-blue-300 bg-blue-50'
                                : 'text-slate-500 border-slate-200'
                            }`}
                        title={data.collapsed ? "展開" : "折りたたみ"}
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
                                        +{data.hiddenDescendantCount} 非表示
                                    </span>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Bottom row: status badge + checklist count */}
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

export default memo(CustomNode);
