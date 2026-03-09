'use client';

import { useState, useMemo, useEffect } from 'react';
import { Search, X, Target, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface ProcessNode {
    id: string;
    label: string;
    phase: string;
    category: string;
}

interface Props {
    nodes: ProcessNode[];
    onSearch: (nodeId: string) => void;
    onClear: () => void;
    highlightedCount: number;
    templateId: string;
    onReverseTreeResult: (nodeIds: string[], edgeIds: string[]) => void;
    currentResultIndex?: number;
    totalResults?: number;
    onNavigateResult?: (direction: 'next' | 'prev') => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export default function GoalSearchBar({
    nodes,
    onSearch,
    onClear,
    highlightedCount,
    templateId,
    onReverseTreeResult,
    currentResultIndex = 0,
    totalResults = 0,
    onNavigateResult
}: Props) {
    const [query, setQuery] = useState('');
    const [isOpen, setIsOpen] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const filtered = useMemo(() => {
        if (!query.trim()) return [];
        const q = query.toLowerCase();
        return nodes.filter(
            n => n.label.toLowerCase().includes(q) ||
                n.phase.toLowerCase().includes(q) ||
                n.category.toLowerCase().includes(q)
        ).slice(0, 10);
    }, [nodes, query]);

    const handleSelect = async (nodeId: string) => {
        setIsOpen(false);
        const node = nodes.find(n => n.id === nodeId);
        if (node) setQuery(node.label);

        try {
            setIsLoading(true);
            setError(null);
            // Call reverse tree API
            const res = await authFetch(
                `${API_BASE}/api/mindmap/tree/${templateId}/${nodeId}`
            );
            if (!res.ok) throw new Error('依存関係の取得に失敗しました');
            const data = await res.json();

            // data.nodes: source nodes, data.edges: source edges
            const nodeIds = data.nodes ? data.nodes.map((n: any) => n.id) : data.path_order || [];
            const edgeIds = data.edges ? data.edges.map((e: any) => e.id) : [];

            if (nodeIds.length === 0) {
                setError('依存ノードが見つかりませんでした');
            } else {
                onReverseTreeResult(nodeIds, edgeIds);
            }
        } catch (err: any) {
            console.error('Reverse tree search error:', err);
            setError(err.message || '検索中にエラーが発生しました');
            // Fallback: local single node highlight
            onSearch(nodeId);
        } finally {
            setIsLoading(false);
        }
    };

    const handleClear = () => {
        setQuery('');
        onClear();
        setIsOpen(false);
    };

    return (
        <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium">
                <Target className="w-4 h-4 text-violet-600" />
                <span>ゴール逆引き検索</span>
            </div>
            <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--muted)]" />
                <input
                    type="text"
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setIsOpen(true);
                    }}
                    onFocus={() => query && setIsOpen(true)}
                    placeholder="例: 鉄骨発注"
                    className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg pl-8 pr-8 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-violet-500 placeholder:text-[var(--muted)]"
                />
                {query && (
                    <button
                        onClick={handleClear}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)] hover:text-[var(--foreground)]"
                    >
                        <X className="w-3.5 h-3.5" />
                    </button>
                )}

                {/* Dropdown */}
                {isOpen && filtered.length > 0 && (
                    <div className="absolute top-full left-0 right-0 mt-1 bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-xl z-50 max-h-60 overflow-y-auto">
                        {filtered.map(node => (
                            <button
                                key={node.id}
                                onClick={() => handleSelect(node.id)}
                                className="w-full text-left px-3 py-2 text-xs hover:bg-[var(--background)] transition-colors flex items-center justify-between"
                            >
                                <span className="font-medium">{node.label}</span>
                                <span className="text-[var(--muted)] text-[10px]">
                                    {node.phase} / {node.category}
                                </span>
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {totalResults > 0 && (
                <div className="flex items-center justify-between px-1 py-1 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="text-[10px] text-slate-500 font-medium ml-1">
                        {currentResultIndex + 1} / {totalResults} 件
                    </div>
                    <div className="flex items-center gap-0.5">
                        <button
                            onClick={() => onNavigateResult?.('prev')}
                            className="p-1 hover:bg-white rounded transition-colors text-slate-400 hover:text-slate-600"
                            title="前へ (Shift+Enter)"
                        >
                            <ChevronLeft className="w-3.5 h-3.5" />
                        </button>
                        <button
                            onClick={() => onNavigateResult?.('next')}
                            className="p-1 hover:bg-white rounded transition-colors text-slate-400 hover:text-slate-600"
                            title="次へ (Enter)"
                        >
                            <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            )}

            {isLoading && (
                <div className="absolute right-10 top-1/2 -translate-y-1/2">
                    <Loader2 className="w-3.5 h-3.5 text-violet-500 animate-spin" />
                </div>
            )}

            {error && (
                <div className="text-[10px] text-red-500 bg-red-50 border border-red-100 rounded px-2 py-1">
                    ⚠️ {error}
                </div>
            )}

            {highlightedCount > 0 && (
                <div className="flex items-center justify-between text-[10px] bg-violet-50 border border-violet-200 rounded-lg px-2.5 py-1.5">
                    <span className="text-violet-700">
                        🔍 {highlightedCount} ノードの依存ツリー表示中
                    </span>
                    <button
                        onClick={handleClear}
                        className="text-violet-600 hover:text-violet-800 underline"
                    >
                        解除
                    </button>
                </div>
            )}
        </div>
    );
}
