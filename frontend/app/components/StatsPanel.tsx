'use client';

import { FileText, Database, Clock, RefreshCw } from 'lucide-react';

interface Stats {
    file_count: number;
    chunk_count: number;
    last_updated: string;
}

interface StatsPanelProps {
    stats: Stats | null;
    onRefresh: () => void;
    isLoading?: boolean;
}

export default function StatsPanel({ stats, onRefresh, isLoading = false }: StatsPanelProps) {
    if (!stats) return null;

    return (
        <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="bg-[var(--card)] p-3 rounded-xl border border-[var(--border)] shadow-sm flex flex-col items-center justify-center text-center">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-full mb-1">
                    <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                </div>
                <span className="text-xl font-bold text-[var(--foreground)]">{stats.file_count}</span>
                <span className="text-[10px] text-[var(--muted)]">Files</span>
            </div>

            <div className="bg-[var(--card)] p-3 rounded-xl border border-[var(--border)] shadow-sm flex flex-col items-center justify-center text-center">
                <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-full mb-1">
                    <Database className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                </div>
                <span className="text-xl font-bold text-[var(--foreground)]">{stats.chunk_count}</span>
                <span className="text-[10px] text-[var(--muted)]">Chunks</span>
            </div>

            <div className="bg-[var(--card)] p-3 rounded-xl border border-[var(--border)] shadow-sm flex flex-col items-center justify-center text-center relative group cursor-pointer" onClick={onRefresh}>
                <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-full mb-1 transition-transform group-hover:scale-110">
                    <Clock className={`w-4 h-4 text-green-600 dark:text-green-400 ${isLoading ? 'animate-spin' : ''}`} />
                </div>
                <span className="text-xs font-medium text-[var(--foreground)] truncate w-full">
                    {stats.last_updated ? new Date(stats.last_updated).toLocaleDateString() : '-'}
                </span>
                <span className="text-[10px] text-[var(--muted)]">Last Updated</span>
            </div>
        </div>
    );
}
