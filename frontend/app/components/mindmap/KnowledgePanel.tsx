'use client';
import { authFetch } from '@/lib/api';

import { useState, useEffect } from 'react';
import { BookOpen, ChevronDown, ChevronRight, Lightbulb, GraduationCap, Wrench } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

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
                const res = await authFetch(`${API_BASE}/api/mindmap/knowledge/${nodeId}`);
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
    // Basic Markdown to HTML converter
    let html = content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        // Convert headers
        .replace(/^### (.*$)/gim, '<h3 style="font-weight:bold;margin-top:8px;margin-bottom:4px">$1</h3>')
        .replace(/^## (.*$)/gim, '<h2 style="font-weight:bold;font-size:1.1em;margin-top:12px;margin-bottom:6px">$1</h2>')
        .replace(/^# (.*$)/gim, '<h1 style="font-weight:bold;font-size:1.2em;margin-top:16px;margin-bottom:8px">$1</h1>')
        // Convert unordered lists
        .replace(/^\s*[-*+] (.*$)/gim, '<li style="margin-left:16px;list-style-type:disc;margin-bottom:2px">$1</li>')
        // Convert ordered lists
        .replace(/^\s*\d+\. (.*$)/gim, '<li style="margin-left:16px;list-style-type:decimal;margin-bottom:2px">$1</li>')
        // Convert blockquotes
        .replace(/^> (.*$)/gim, '<blockquote style="border-left:3px solid #ccc;padding-left:8px;color:#666;margin:4px 0">$1</blockquote>')
        // Handle code blocks
        .replace(/`([^`]+)`/g, '<code style="background-color:#f1f5f9;padding:2px 4px;border-radius:4px;font-family:monospace;font-size:0.9em">$1</code>');

    // Handle simple tables
    const tableRegex = /((?:\|.+)+\|)\n/g;
    html = html.replace(tableRegex, (match) => {
        if (match.includes('---')) return ''; // Skip separator row
        const cells = match.split('|').filter(Boolean).map(c => c.trim());
        return `<div style="display:flex;gap:8px;font-size:10px;padding:4px;border-bottom:1px solid #e2e8f0">${cells.map(c => `<span style="flex:1">${c}</span>`).join('')}</div>`;
    });

    // Replace double newlines with breaks, while preserving list elements
    html = html.replace(/\n\n/g, '<br/><br/>');
    html = html.replace(/\n(?!(<li|<blockquote|<h|<div))/g, '<br/>');

    // Wrap consecutive li elements in ul
    html = html.replace(/(<li style="margin-left:16px;list-style-type:disc.*?>.*?<\/li>(?:<br\/>)*)+/g, match => `<ul style="margin:4px 0">${match.replace(/<br\/>/g, '')}</ul>`);
    html = html.replace(/(<li style="margin-left:16px;list-style-type:decimal.*?>.*?<\/li>(?:<br\/>)*)+/g, match => `<ol style="margin:4px 0">${match.replace(/<br\/>/g, '')}</ol>`);

    return html;
}
