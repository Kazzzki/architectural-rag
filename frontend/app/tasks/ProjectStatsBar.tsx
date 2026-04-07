'use client';

import React, { useMemo } from 'react';
import type { Task } from './types';

interface Props {
  tasks: Task[];
  projectName: string;
}

export default function ProjectStatsBar({ tasks, projectName }: Props) {
  const stats = useMemo(() => {
    const projectTasks = tasks.filter((t) => !t.parent_id && t.project_name === projectName);
    const total = projectTasks.length;
    if (total === 0) return null;

    const done = projectTasks.filter((t) => t.status === 'done').length;
    const inProgress = projectTasks.filter((t) => t.status === 'in_progress').length;
    const today = new Date().toISOString().slice(0, 10);
    const overdue = projectTasks.filter(
      (t) => t.status !== 'done' && t.due_date && t.due_date < today
    ).length;
    const completionRate = Math.round((done / total) * 100);

    return { total, done, inProgress, overdue, completionRate };
  }, [tasks, projectName]);

  if (!stats) return null;

  const barColor = stats.overdue > 0 ? 'bg-red-500' : 'bg-gray-700';

  return (
    <div className="bg-white border-b border-gray-200 px-3 md:px-6 py-2">
      <div className="max-w-7xl mx-auto flex items-center gap-4 sm:gap-6">
        <div className="flex items-center gap-2 flex-1 max-w-xs">
          <div className="flex-1 bg-gray-100 rounded-full h-2">
            <div className={`${barColor} h-2 rounded-full transition-all`}
              style={{ width: `${stats.completionRate}%` }} />
          </div>
          <span className="text-xs text-gray-500 whitespace-nowrap font-medium">{stats.completionRate}%</span>
        </div>

        <div className="flex items-center gap-3 sm:gap-4 text-xs">
          <span className="text-gray-500">全 <strong className="text-gray-900">{stats.total}</strong></span>
          <span className="text-gray-500">進行 <strong className="text-blue-600">{stats.inProgress}</strong></span>
          <span className="text-gray-500">完了 <strong className="text-green-600">{stats.done}</strong></span>
          {stats.overdue > 0 && (
            <span className="text-gray-500">超過 <strong className="text-red-600">{stats.overdue}</strong></span>
          )}
        </div>
      </div>
    </div>
  );
}
