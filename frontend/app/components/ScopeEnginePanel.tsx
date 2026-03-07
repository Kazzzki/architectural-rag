import React, { useEffect, useState } from 'react';
import { Building2, Globe, Sparkles, ChevronDown } from 'lucide-react';
import { fetchProjects, fetchActiveScope, updateActiveScope, ProjectInfo } from '@/lib/api';

interface ScopeEnginePanelProps {
    onScopeChange: (projectId: string | null, scopeMode: string) => void;
}

export default function ScopeEnginePanel({ onScopeChange }: ScopeEnginePanelProps) {
    const [projects, setProjects] = useState<ProjectInfo[]>([]);
    const [projectId, setProjectId] = useState<string | null>(null);
    const [scopeMode, setScopeMode] = useState<string>('auto');
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        async function load() {
            try {
                const [projData, scopeData] = await Promise.all([
                    fetchProjects(),
                    fetchActiveScope()
                ]);
                setProjects(projData);
                setProjectId(scopeData.project_id);
                setScopeMode(scopeData.scope_mode);
                onScopeChange(scopeData.project_id, scopeData.scope_mode);
            } catch (err) {
                console.error("Failed to load scope panel", err);
            } finally {
                setIsLoading(false);
            }
        }
        load();
    }, [onScopeChange]);

    const handleModeChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
        const newMode = e.target.value;
        setScopeMode(newMode);
        onScopeChange(projectId, newMode);
        await updateActiveScope(projectId, newMode);
    };

    const handleProjectChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
        const newProjId = e.target.value || null;
        setProjectId(newProjId);
        onScopeChange(newProjId, scopeMode);
        await updateActiveScope(newProjId, scopeMode);
    };

    if (isLoading) return <div className="p-4 text-xs text-[var(--muted)]">Loading context scope...</div>;

    return (
        <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)] shadow-sm flex flex-col gap-3">
            <div className="flex items-center gap-2 font-medium text-sm text-[var(--foreground)]">
                <Globe className="w-4 h-4 text-primary-500" />
                動作コンテキスト (Scope)
            </div>

            <div className="flex flex-col gap-2 relative">
                <label className="text-[10px] uppercase font-bold text-[var(--muted)] tracking-wider">Mode</label>
                <div className="relative">
                    <select
                        value={scopeMode}
                        onChange={handleModeChange}
                        className="w-full appearance-none bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-xs text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-primary-500 pr-8"
                    >
                        <option value="auto">🌟 自動判定 (Auto)</option>
                        <option value="explicit">📌 個別案件に固定 (Explicit)</option>
                        <option value="global">🌍 案件非依存 (Global)</option>
                    </select>
                    <ChevronDown className="absolute right-2.5 top-[50%] -translate-y-[50%] w-3.5 h-3.5 text-[var(--muted)] pointer-events-none" />
                </div>
            </div>

            <div className={`flex flex-col gap-2 relative transition-opacity ${scopeMode === 'global' ? 'opacity-50 pointer-events-none' : ''}`}>
                <label className="text-[10px] uppercase font-bold text-[var(--muted)] tracking-wider">Project</label>
                <div className="relative">
                    <select
                        value={projectId || ''}
                        onChange={handleProjectChange}
                        className="w-full appearance-none bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-xs text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-primary-500 pr-8"
                    >
                        <option value="">(未選択)</option>
                        {projects.map(p => (
                            <option key={p.id} value={p.id}>
                                {p.name} {p.building_type ? `(${p.building_type})` : ''}
                            </option>
                        ))}
                    </select>
                    <ChevronDown className="absolute right-2.5 top-[50%] -translate-y-[50%] w-3.5 h-3.5 text-[var(--muted)] pointer-events-none" />
                </div>
            </div>
        </div>
    );
}
