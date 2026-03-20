'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FolderOpen, Check, BarChart3 } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface ProjectSummary {
  project_name: string;
  issue_count: number;
}

interface Props {
  onProjectChange?: (projectName: string | null) => void;
}

export default function ProjectSwitcher({ onProjectChange }: Props) {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    // Fetch active project
    authFetch('/api/system/active-project').then(r => r.json())
      .then(d => setActiveProject(d.project_name || null))
      .catch(() => {});
    // Fetch project list
    authFetch('/api/issues/projects-summary').then(r => r.json())
      .then(d => setProjects(d.projects || []))
      .catch(() => {});
  }, []);

  const selectProject = useCallback(async (name: string | null) => {
    setActiveProject(name);
    setOpen(false);
    await authFetch('/api/system/active-project', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: name }),
    }).catch(() => {});
    onProjectChange?.(name);
  }, [onProjectChange]);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        title={activeProject || '全プロジェクト'}
        className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors
          ${activeProject ? 'text-indigo-600 bg-indigo-100' : 'text-gray-500 hover:bg-gray-200'}`}
      >
        <FolderOpen className="w-5 h-5" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute left-12 top-0 z-40 bg-white border border-gray-200 rounded-xl shadow-xl min-w-[200px] py-1">
            <div className="px-3 py-2 text-xs font-medium text-gray-400 border-b border-gray-100">
              プロジェクト切替
            </div>

            <button
              onClick={() => selectProject(null)}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 transition-colors"
            >
              <span className="w-4">{activeProject === null && <Check className="w-4 h-4 text-indigo-600" />}</span>
              <span className="text-gray-600">全プロジェクト</span>
            </button>

            {projects.map(p => (
              <div key={p.project_name} className="flex items-center hover:bg-gray-50 transition-colors">
                <button
                  onClick={() => selectProject(p.project_name)}
                  className="flex-1 flex items-center gap-2 px-3 py-2 text-sm"
                >
                  <span className="w-4">{activeProject === p.project_name && <Check className="w-4 h-4 text-indigo-600" />}</span>
                  <span className="text-gray-800 truncate flex-1 text-left">{p.project_name}</span>
                  <span className="text-xs text-gray-400">{p.issue_count}</span>
                </button>
                <button
                  onClick={() => { setOpen(false); router.push(`/projects/${encodeURIComponent(p.project_name)}`); }}
                  className="px-2 py-2 text-gray-400 hover:text-indigo-600"
                  title="ダッシュボード"
                >
                  <BarChart3 className="w-5 h-5" />
                </button>
              </div>
            ))}

            {projects.length === 0 && (
              <div className="px-3 py-4 text-xs text-gray-400 text-center">
                プロジェクトがありません
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
