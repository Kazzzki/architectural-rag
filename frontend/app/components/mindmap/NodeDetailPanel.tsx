'use client';

import { X, CheckSquare, FileText, Users, ArrowRight, ArrowLeft, ExternalLink, BookOpen, ClipboardList } from 'lucide-react';
import KnowledgePanel from './KnowledgePanel';
import ResearchTab from './ResearchTab';

interface ProcessNode {
    id: string;
    label: string;
    description: string;
    phase: string;
    category: string;
    checklist: string[];
    deliverables: string[];
    key_stakeholders: string[];
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
    node: ProcessNode;
    incomingEdges: EdgeData[];
    outgoingEdges: EdgeData[];
    getNodeLabel: (nodeId: string) => string;
    categoryColor: string;
    onClose: () => void;
    onNavigate: (nodeId: string) => void;
    isEditMode?: boolean;
    onStatusChange?: (nodeId: string, newStatus: string) => void;
    phases?: string[];
    categories?: string[];
    onUpdate?: (nodeId: string, updates: Partial<ProcessNode>) => void;
}

const STATUS_OPTIONS = ['未着手', '検討中', '決定済み'];

const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
    '未着手': { label: '未着手', bg: 'bg-slate-100', text: 'text-slate-500' },
    '検討中': { label: '検討中', bg: 'bg-amber-100', text: 'text-amber-700' },
    '決定済み': { label: '決定済み', bg: 'bg-green-100', text: 'text-green-700' },
};

export default function NodeDetailPanel({
    node,
    incomingEdges,
    outgoingEdges,
    getNodeLabel,
    categoryColor,
    onClose,
    onNavigate,
    isEditMode = false,
    onStatusChange,
    phases = [],
    categories = [],
    onUpdate,
}: Props) {
    const statusCfg = STATUS_CONFIG[node.status] || STATUS_CONFIG['未着手'];

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <div
                className="p-4 border-b border-[var(--border)] relative"
                style={{ background: `linear-gradient(135deg, ${categoryColor}15, transparent)` }}
            >
                <button
                    onClick={onClose}
                    className="absolute top-3 right-3 text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                >
                    <X className="w-4 h-4" />
                </button>

                <div className="flex items-center gap-2 mb-2">
                    {isEditMode && onUpdate ? (
                        <>
                            <select
                                value={node.phase}
                                onChange={(e) => onUpdate(node.id, { phase: e.target.value })}
                                className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border border-[var(--border)] bg-white/50"
                                style={{ color: categoryColor }}
                            >
                                {phases.map(p => <option key={p} value={p}>{p}</option>)}
                            </select>
                            <select
                                value={node.category}
                                onChange={(e) => onUpdate(node.id, { category: e.target.value })}
                                className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border border-[var(--border)] bg-white/50"
                                style={{ color: categoryColor }}
                            >
                                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </>
                    ) : (
                        <>
                            <span
                                className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
                                style={{ backgroundColor: `${categoryColor}25`, color: categoryColor }}
                            >
                                {node.phase}
                            </span>
                            <span
                                className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
                                style={{ backgroundColor: `${categoryColor}15`, color: categoryColor }}
                            >
                                {node.category}
                            </span>
                        </>
                    )}
                </div>

                <h2 className="text-lg font-bold pr-6">{node.label}</h2>
                <p className="text-xs text-[var(--muted)] mt-1 leading-relaxed">{node.description}</p>

                {/* Status - editable in edit mode */}
                <div className="mt-3">
                    {isEditMode && onStatusChange ? (
                        <div className="flex items-center gap-1.5">
                            {STATUS_OPTIONS.map(status => {
                                const cfg = STATUS_CONFIG[status];
                                return (
                                    <button
                                        key={status}
                                        onClick={() => onStatusChange(node.id, status)}
                                        className={`text-xs font-medium px-2.5 py-1 rounded-full transition-all ${node.status === status
                                            ? `${cfg.bg} ${cfg.text} ring-1 ring-current`
                                            : 'bg-[var(--background)] text-[var(--muted)] hover:text-[var(--foreground)]'
                                            }`}
                                    >
                                        {cfg.label}
                                    </button>
                                );
                            })}
                        </div>
                    ) : (
                        <span className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full ${statusCfg.bg} ${statusCfg.text}`}>
                            {statusCfg.label}
                        </span>
                    )}
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-5">
                {/* Knowledge Panel (Phase 3) */}
                <section>
                    <h3 className="flex items-center gap-2 text-sm font-bold mb-2">
                        <BookOpen className="w-4 h-4" style={{ color: categoryColor }} />
                        知識・ナレッジ
                    </h3>
                    <KnowledgePanel nodeId={node.id} categoryColor={categoryColor} />
                </section>

                {/* Research Planner Panel */}
                <section>
                    <h3 className="flex items-center gap-2 text-sm font-bold mb-2">
                        <ClipboardList className="w-4 h-4" style={{ color: categoryColor }} />
                        リサーチ・調査プラン
                    </h3>
                    <ResearchTab node={node as any} onUpdate={onUpdate} />
                </section>

                {/* Checklist */}
                {node.checklist.length > 0 && (
                    <section>
                        <h3 className="flex items-center gap-2 text-sm font-bold mb-2">
                            <CheckSquare className="w-4 h-4" style={{ color: categoryColor }} />
                            確認チェックリスト
                        </h3>
                        <div className="space-y-1.5">
                            {node.checklist.map((item, i) => (
                                <div key={i} className="flex items-start gap-2 text-xs">
                                    <div className="w-4 h-4 rounded border border-[var(--border)] flex-shrink-0 mt-0.5" />
                                    <span className="text-[var(--foreground)] leading-relaxed">{item}</span>
                                </div>
                            ))}
                        </div>
                    </section>
                )}

                {/* Deliverables */}
                {node.deliverables.length > 0 && (
                    <section>
                        <h3 className="flex items-center gap-2 text-sm font-bold mb-2">
                            <FileText className="w-4 h-4" style={{ color: categoryColor }} />
                            成果物
                        </h3>
                        <div className="space-y-1">
                            {node.deliverables.map((item, i) => (
                                <div key={i} className="text-xs text-[var(--foreground)] bg-[var(--background)] rounded-lg px-3 py-1.5">
                                    📄 {item}
                                </div>
                            ))}
                        </div>
                    </section>
                )}

                {/* Stakeholders */}
                {node.key_stakeholders.length > 0 && (
                    <section>
                        <h3 className="flex items-center gap-2 text-sm font-bold mb-2">
                            <Users className="w-4 h-4" style={{ color: categoryColor }} />
                            関係者
                        </h3>
                        <div className="flex flex-wrap gap-1.5">
                            {node.key_stakeholders.map((item, i) => (
                                <span key={i} className="text-xs bg-[var(--background)] border border-[var(--border)] rounded-full px-2.5 py-1">
                                    {item}
                                </span>
                            ))}
                        </div>
                    </section>
                )}

                {/* Dependencies: Incoming */}
                {incomingEdges.length > 0 && (
                    <section>
                        <h3 className="flex items-center gap-2 text-sm font-bold mb-2">
                            <ArrowLeft className="w-4 h-4 text-blue-500" />
                            先行タスク（これが必要）
                        </h3>
                        <div className="space-y-1.5">
                            {incomingEdges.map(edge => (
                                <button
                                    key={edge.id}
                                    onClick={() => onNavigate(edge.source)}
                                    className="w-full text-left bg-[var(--background)] hover:bg-blue-50 border border-[var(--border)] hover:border-blue-300 rounded-lg px-3 py-2 transition-colors group"
                                >
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-medium group-hover:text-blue-600 transition-colors">
                                            {getNodeLabel(edge.source)}
                                        </span>
                                        <ExternalLink className="w-3 h-3 text-[var(--muted)] group-hover:text-blue-600" />
                                    </div>
                                    {edge.reason && (
                                        <p className="text-[10px] text-[var(--muted)] mt-1">{edge.reason}</p>
                                    )}
                                    <span className={`text-[9px] mt-1 inline-block px-1.5 py-0.5 rounded ${edge.type === 'hard' ? 'bg-red-100 text-red-600' : 'bg-slate-100 text-slate-500'}`}>
                                        {edge.type === 'hard' ? '必須' : '推奨'}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </section>
                )}

                {/* Dependencies: Outgoing */}
                {outgoingEdges.length > 0 && (
                    <section>
                        <h3 className="flex items-center gap-2 text-sm font-bold mb-2">
                            <ArrowRight className="w-4 h-4 text-green-600" />
                            後続タスク（これで可能に）
                        </h3>
                        <div className="space-y-1.5">
                            {outgoingEdges.map(edge => (
                                <button
                                    key={edge.id}
                                    onClick={() => onNavigate(edge.target)}
                                    className="w-full text-left bg-[var(--background)] hover:bg-green-50 border border-[var(--border)] hover:border-green-300 rounded-lg px-3 py-2 transition-colors group"
                                >
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-medium group-hover:text-green-600 transition-colors">
                                            {getNodeLabel(edge.target)}
                                        </span>
                                        <ExternalLink className="w-3 h-3 text-[var(--muted)] group-hover:text-green-600" />
                                    </div>
                                    {edge.reason && (
                                        <p className="text-[10px] text-[var(--muted)] mt-1">{edge.reason}</p>
                                    )}
                                    <span className={`text-[9px] mt-1 inline-block px-1.5 py-0.5 rounded ${edge.type === 'hard' ? 'bg-red-100 text-red-600' : 'bg-slate-100 text-slate-500'}`}>
                                        {edge.type === 'hard' ? '必須' : '推奨'}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </div>
    );
}
