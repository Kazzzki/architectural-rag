'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Loader2, FolderOpen, ListChecks, CheckCircle2, AlertTriangle, TrendingUp } from 'lucide-react';
import { api } from './taskApi';

interface ProjectSummary {
  project_name: string;
  total: number;
  done: number;
  in_progress: number;
  todo: number;
  overdue: number;
  completion_rate: number;
  earliest_due?: string;
  latest_due?: string;
  priority_high?: number;
  priority_medium?: number;
  priority_low?: number;
}

export default function PortfolioDashboard() {
  const [data, setData] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const result = await api.getPortfolio();
        setData(result ?? []);
      } catch (e) {
        console.warn('portfolio load:', e);
        setData([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const globalStats = useMemo(() => {
    const total = data.reduce((s, p) => s + p.total, 0);
    const done = data.reduce((s, p) => s + p.done, 0);
    const overdue = data.reduce((s, p) => s + p.overdue, 0);
    return {
      total,
      done,
      overdue,
      completionRate: total === 0 ? 0 : Math.round((done / total) * 100),
    };
  }, [data]);

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>;
  }

  if (data.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <FolderOpen className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">プロジェクトデータがありません</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Global Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon={<ListChecks className="w-4 h-4 text-gray-400" />} label="全タスク" value={globalStats.total} />
        <StatCard icon={<CheckCircle2 className="w-4 h-4 text-green-500" />} label="完了済み" value={globalStats.done} accent="text-green-600" />
        <StatCard icon={<AlertTriangle className="w-4 h-4 text-red-500" />} label="期限超過" value={globalStats.overdue}
          accent={globalStats.overdue > 0 ? 'text-red-600' : undefined} />
        <StatCard icon={<TrendingUp className="w-4 h-4 text-blue-500" />} label="完了率" value={`${globalStats.completionRate}%`} accent="text-blue-600" />
      </div>

      {/* Project Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((p) => (
          <ProjectCard key={p.project_name} project={p} />
        ))}
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, accent }: {
  icon: React.ReactNode; label: string; value: number | string; accent?: string;
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3 sm:p-4">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-xs text-gray-500">{label}</span>
      </div>
      <span className={`text-xl sm:text-2xl font-bold ${accent || 'text-gray-900'}`}>{value}</span>
    </div>
  );
}

function ProjectCard({ project: p }: { project: ProjectSummary }) {
  const barColor = p.overdue > 0 ? 'bg-red-500' : 'bg-gray-700';
  const totalActive = (p.priority_high ?? 0) + (p.priority_medium ?? 0) + (p.priority_low ?? 0);

  return (
    <div className="bg-white rounded-md border border-gray-200 p-3 sm:p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 truncate">{p.project_name}</h3>
        <span className="text-lg font-bold text-gray-900">{p.completion_rate}%</span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-100 rounded-full h-2 mb-3">
        <div className={`${barColor} h-2 rounded-full transition-all`}
          style={{ width: `${p.completion_rate}%` }} />
      </div>

      <div className="grid grid-cols-4 gap-2 text-center mb-3">
        <div>
          <p className="text-sm font-bold text-gray-900">{p.total}</p>
          <p className="text-[10px] text-gray-400">全</p>
        </div>
        <div>
          <p className="text-sm font-bold text-blue-600">{p.in_progress}</p>
          <p className="text-[10px] text-gray-400">進行中</p>
        </div>
        <div>
          <p className="text-sm font-bold text-green-600">{p.done}</p>
          <p className="text-[10px] text-gray-400">完了</p>
        </div>
        <div>
          <p className={`text-sm font-bold ${p.overdue > 0 ? 'text-red-600' : 'text-gray-300'}`}>{p.overdue}</p>
          <p className="text-[10px] text-gray-400">超過</p>
        </div>
      </div>

      {/* Priority distribution bar */}
      {totalActive > 0 && (
        <div className="flex h-1.5 rounded-full overflow-hidden bg-gray-100">
          {(p.priority_high ?? 0) > 0 && (
            <div className="h-full bg-red-500" style={{ width: `${((p.priority_high ?? 0) / totalActive) * 100}%` }} />
          )}
          {(p.priority_medium ?? 0) > 0 && (
            <div className="h-full bg-amber-400" style={{ width: `${((p.priority_medium ?? 0) / totalActive) * 100}%` }} />
          )}
          {(p.priority_low ?? 0) > 0 && (
            <div className="h-full bg-gray-300" style={{ width: `${((p.priority_low ?? 0) / totalActive) * 100}%` }} />
          )}
        </div>
      )}
    </div>
  );
}
