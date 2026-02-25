'use client';
import { authFetch } from '@/lib/api';

import { useState, useEffect } from 'react';
import { FolderOpen, Plus, Trash2, Clock, ChevronDown } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

interface Project {
    id: string;
    name: string;
    description: string;
    template_id: string;
    created_at: string;
    updated_at: string;
    node_count: number;
}

interface Props {
    templateId: string;
    templateName: string;
    currentProjectId: string | null;
    onProjectSelect: (projectId: string | null) => void;
    onProjectCreated: (projectId: string) => void;
}

export default function ProjectSelector({ templateId, templateName, currentProjectId, onProjectSelect, onProjectCreated }: Props) {
    const [projects, setProjects] = useState<Project[]>([]);
    const [isOpen, setIsOpen] = useState(false);
    const [showCreate, setShowCreate] = useState(false);
    const [newName, setNewName] = useState('');
    const [creating, setCreating] = useState(false);

    const fetchProjects = async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/projects`);
            const data = await res.json();
            setProjects(data.filter((p: Project) => p.template_id === templateId));
        } catch (err) {
            console.error('Project list error:', err);
        }
    };

    useEffect(() => {
        fetchProjects();
    }, [templateId]);

    const handleCreate = async () => {
        if (!newName.trim()) return;
        setCreating(true);
        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/projects`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName.trim(), template_id: templateId }),
            });
            const data = await res.json();
            await fetchProjects();
            onProjectCreated(data.id);
            setNewName('');
            setShowCreate(false);
        } catch (err) {
            console.error('Project create error:', err);
        }
        setCreating(false);
    };

    const handleDelete = async (projectId: string, e: React.MouseEvent) => {
        e.stopPropagation();
        if (!confirm('このプロジェクトを削除しますか？')) return;
        try {
            await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}`, { method: 'DELETE' });
            if (currentProjectId === projectId) onProjectSelect(null);
            await fetchProjects();
        } catch (err) {
            console.error('Delete error:', err);
        }
    };

    const currentProject = projects.find(p => p.id === currentProjectId);

    return (
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center justify-between px-3 py-2.5 bg-[var(--background)] border border-[var(--border)] rounded-lg text-sm hover:border-violet-500/50 transition-colors"
            >
                <span className="flex items-center gap-2 truncate">
                    <FolderOpen className="w-4 h-4 text-violet-400 flex-shrink-0" />
                    {currentProject ? (
                        <span className="truncate">{currentProject.name}</span>
                    ) : (
                        <span className="text-[var(--muted)]">テンプレート（閲覧のみ）</span>
                    )}
                </span>
                <ChevronDown className={`w-4 h-4 text-[var(--muted)] transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-2xl z-50 overflow-hidden">
                    {/* Template mode (read-only) */}
                    <button
                        onClick={() => { onProjectSelect(null); setIsOpen(false); }}
                        className={`w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-[var(--background)] transition-colors ${!currentProjectId ? 'bg-violet-500/10 text-violet-300' : ''
                            }`}
                    >
                        📋 {templateName}（テンプレート）
                    </button>

                    <div className="border-t border-[var(--border)]" />

                    {projects.map(p => (
                        <button
                            key={p.id}
                            onClick={() => { onProjectSelect(p.id); setIsOpen(false); }}
                            className={`w-full flex items-center justify-between px-3 py-2 text-xs text-left hover:bg-[var(--background)] transition-colors group ${currentProjectId === p.id ? 'bg-violet-500/10 text-violet-300' : ''
                                }`}
                        >
                            <span className="flex items-center gap-2 truncate">
                                <FolderOpen className="w-3.5 h-3.5" />
                                <span className="truncate">{p.name}</span>
                                <span className="text-[var(--muted)] text-[10px]">{p.node_count}ノード</span>
                            </span>
                            <button
                                onClick={(e) => handleDelete(p.id, e)}
                                className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 p-0.5"
                            >
                                <Trash2 className="w-3 h-3" />
                            </button>
                        </button>
                    ))}

                    <div className="border-t border-[var(--border)]" />

                    {showCreate ? (
                        <div className="p-2 flex gap-2">
                            <input
                                type="text"
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                                placeholder="プロジェクト名..."
                                className="flex-1 bg-[var(--background)] border border-[var(--border)] rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500"
                                autoFocus
                            />
                            <button
                                onClick={handleCreate}
                                disabled={creating || !newName.trim()}
                                className="px-2 py-1 bg-violet-500 text-white rounded text-xs hover:bg-violet-600 disabled:opacity-40"
                            >
                                {creating ? '...' : '作成'}
                            </button>
                        </div>
                    ) : (
                        <button
                            onClick={() => setShowCreate(true)}
                            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-green-400 hover:bg-green-500/10 transition-colors"
                        >
                            <Plus className="w-3.5 h-3.5" />
                            新規プロジェクト作成
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
