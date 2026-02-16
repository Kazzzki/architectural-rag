'use client';

import { useState, useEffect } from 'react';
import { BookOpen, ChevronDown, ChevronRight, Lightbulb, GraduationCap, Wrench } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface KnowledgeEntry {
    depth: string;
    title: string;
    content: string;
    references: string[];
}

interface Props {
    nodeId: string;
    categoryColor: string;
}

const DEPTH_CONFIG: Record<string, { icon: typeof Lightbulb; label: string; bg: string; text: string }> = {
    overview: { icon: Lightbulb, label: '概要', bg: 'bg-blue-100', text: 'text-blue-600' },
    practical: { icon: Wrench, label: '実践', bg: 'bg-green-100', text: 'text-green-600' },
    expert: { icon: GraduationCap, label: '専門', bg: 'bg-purple-100', text: 'text-purple-600' },
};

export default function KnowledgePanel({ nodeId, categoryColor }: Props) {
    const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
    const [expandedDepths, setExpandedDepths] = useState<Set<string>>(new Set(['overview']));
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const fetchKnowledge = async () => {
            setLoading(true);
            try {
                const res = await fetch(`${API_BASE}/api/mindmap/knowledge/${nodeId}`);
                const data = await res.json();
                setEntries(data.entries || []);
            } catch (err) {
                console.error('Knowledge fetch error:', err);
                setEntries([]);
            }
            setLoading(false);
        };
        fetchKnowledge();
    }, [nodeId]);

    const toggleDepth = (depth: string) => {
        setExpandedDepths(prev => {
            const next = new Set(prev);
            if (next.has(depth)) next.delete(depth);
            else next.add(depth);
            return next;
        });
    };

    if (loading) {
        return (
            <div className="text-xs text-[var(--muted)] text-center py-4 animate-pulse">
                知識データを読み込み中...
            </div>
        );
    }

    if (entries.length === 0) {
        return (
            <div className="text-xs text-[var(--muted)] text-center py-3 bg-[var(--background)] rounded-lg">
                📚 このノードの知識データはまだありません
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {entries.map((entry, i) => {
                const config = DEPTH_CONFIG[entry.depth] || DEPTH_CONFIG.overview;
                const Icon = config.icon;
                const isExpanded = expandedDepths.has(entry.depth);

                return (
                    <div key={i} className="border border-[var(--border)] rounded-lg overflow-hidden">
                        <button
                            onClick={() => toggleDepth(entry.depth)}
                            className={`w-full flex items-center justify-between px-3 py-2 text-left hover:bg-[var(--background)] transition-colors`}
                        >
                            <span className="flex items-center gap-2">
                                <span className={`flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${config.bg} ${config.text}`}>
                                    <Icon className="w-3 h-3" />
                                    {config.label}
                                </span>
                                <span className="text-xs font-medium">{entry.title}</span>
                            </span>
                            {isExpanded
                                ? <ChevronDown className="w-3.5 h-3.5 text-[var(--muted)]" />
                                : <ChevronRight className="w-3.5 h-3.5 text-[var(--muted)]" />
                            }
                        </button>

                        {isExpanded && (
                            <div className="px-3 pb-3 border-t border-[var(--border)]">
                                <div
                                    className="text-xs text-[var(--foreground)] leading-relaxed mt-2 space-y-2 knowledge-content"
                                    dangerouslySetInnerHTML={{ __html: formatContent(entry.content) }}
                                />
                                {entry.references.length > 0 && (
                                    <div className="mt-2 pt-2 border-t border-[var(--border)]">
                                        <p className="text-[10px] font-bold text-[var(--muted)] mb-1">参考文献</p>
                                        {entry.references.map((ref, j) => (
                                            <p key={j} className="text-[10px] text-[var(--muted)] italic">📖 {ref}</p>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

function formatContent(content: string): string {
    // Simple markdown-like formatting
    return content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.+)$/gm, '<li style="margin-left:12px;list-style:disc">$1</li>')
        .replace(/^(\d+)\. (.+)$/gm, '<li style="margin-left:12px;list-style:decimal">$2</li>')
        .replace(/\|(.+)\|/g, (match) => {
            // Simple table rendering
            const cells = match.split('|').filter(Boolean).map(c => c.trim());
            return `<div style="display:flex;gap:8px;font-size:10px;padding:2px 0">${cells.map(c => `<span style="flex:1">${c}</span>`).join('')}</div>`;
        })
        .replace(/\n\n/g, '<br/><br/>')
        .replace(/\n/g, '<br/>');
}
