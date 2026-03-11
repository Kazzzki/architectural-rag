import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FolderOpen, ExternalLink, Plus, GitBranch, Target, Clock, RefreshCw } from 'lucide-react';
import { authFetch } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

interface ProjectItem {
    id: string;
    name: string;
    description: string;
    building_type: string;
    status: string;
    updated_at: string;
    progress: {
        total: number;
        completed: number;
        in_progress: number;
        percent: number;
    };
}

export default function MindmapPanel() {
    const router = useRouter();
    const [projects, setProjects] = useState<ProjectItem[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchProjects = async () => {
        setLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/projects`);
            if (res.ok) {
                setProjects(await res.json());
            }
        } catch (err) {
            console.error('Projects load error:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProjects();
    }, []);

    const formatDate = (iso: string) => {
        const d = new Date(iso);
        return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    };

    return (
        <div className="flex flex-col h-full bg-[var(--background)] text-[var(--foreground)]">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)] shrink-0 bg-white">
                <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
                        <GitBranch className="w-3.5 h-3.5 text-white" />
                    </div>
                    <span className="font-bold text-sm tracking-tight text-[var(--foreground)]">プロジェクト一覧</span>
                </div>
                <div className="flex items-center gap-1">
                    <button 
                        onClick={fetchProjects} 
                        className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-colors text-slate-500" 
                        title="更新"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                    <Link
                        href="/mindmap"
                        className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-colors text-slate-500"
                        title="新規作成画面へ"
                    >
                        <Plus className="w-4 h-4" />
                    </Link>
                </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-3">
                {loading ? (
                    <div className="flex justify-center py-10">
                        <div className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                ) : projects.length === 0 ? (
                    <div className="text-center py-10">
                        <FolderOpen className="w-8 h-8 mx-auto mb-2 text-[var(--muted)] opacity-50" />
                        <p className="text-sm font-medium mb-1">プロジェクトなし</p>
                        <p className="text-xs text-[var(--muted)]">フル画面から作成してください</p>
                    </div>
                ) : (
                    projects.map(project => (
                        <div
                            key={project.id}
                            onClick={() => router.push(`/mindmap/projects/${project.id}`)}
                            className="group bg-white border border-[var(--border)] rounded-lg p-3 cursor-pointer hover:border-violet-400 hover:shadow-sm transition-all"
                        >
                            <div className="flex justify-between items-start mb-1.5">
                                <h3 className="font-semibold text-sm text-[var(--foreground)] group-hover:text-violet-700 transition-colors line-clamp-1">
                                    {project.name}
                                </h3>
                            </div>
                            
                            <p className="text-xs text-[var(--muted)] mb-2 line-clamp-1">{project.description}</p>
                            
                            <div className="flex items-center justify-between text-[10px] text-[var(--muted)] mb-1">
                                <span className="flex items-center gap-1">
                                    <Target className="w-3 h-3 text-violet-500" />
                                    {project.progress.percent}%
                                </span>
                                <span className="flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {formatDate(project.updated_at)}
                                </span>
                            </div>
                            <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                <div
                                    className="h-full rounded-full transition-all duration-500"
                                    style={{
                                        width: `${project.progress.percent}%`,
                                        background: project.progress.percent === 100
                                            ? 'linear-gradient(to right, #22c55e, #10b981)'
                                            : 'linear-gradient(to right, #8b5cf6, #d946ef)',
                                    }}
                                />
                            </div>
                        </div>
                    ))
                )}
            </div>

            {/* Footer full screen link */}
            <div className="p-3 border-t border-[var(--border)] bg-slate-50 shrink-0">
                <Link 
                    href="/mindmap"
                    className="flex items-center justify-center gap-2 w-full py-2 bg-white border border-[var(--border)] rounded-lg text-xs font-medium text-[var(--foreground)] hover:bg-slate-100 transition-colors shadow-sm"
                >
                    <ExternalLink className="w-3.5 h-3.5" />
                    フル画面で開く
                </Link>
            </div>
        </div>
    );
}
