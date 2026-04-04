'use client';

import React from 'react';
import { AlertCircle, Clock, Bell, CheckSquare } from 'lucide-react';
import type { Task } from './types';
import { PRIORITY_LABEL, formatDate } from './types';

export default function TodayView({
  tasks,
  onTaskClick,
  onToggleDone,
}: {
  tasks: Task[];
  onTaskClick: (task: Task) => void;
  onToggleDone: (task: Task) => void;
}) {
  const todayStr = new Date().toISOString().slice(0, 10);

  const overdue = tasks.filter(
    (t) => t.due_date && t.due_date.slice(0, 10) < todayStr && t.status !== 'done'
  );
  const todayTasks = tasks.filter(
    (t) => t.due_date?.slice(0, 10) === todayStr && t.status !== 'done'
  );
  const inProgress = tasks.filter(
    (t) => t.status === 'in_progress' && !overdue.includes(t) && !todayTasks.includes(t)
  );
  const recentlyDone = tasks
    .filter((t) => t.status === 'done' && t.updated_at?.slice(0, 10) === todayStr)
    .slice(0, 5);

  const totalEstimated = [...overdue, ...todayTasks, ...inProgress].reduce(
    (sum, t) => sum + (t.estimated_minutes ?? 0), 0
  );

  const Section = ({ title, icon, color, items }: { title: string; icon: React.ReactNode; color: string; items: Task[] }) => (
    items.length > 0 ? (
      <div className="mb-6">
        <div className={`flex items-center gap-2 mb-3 ${color}`}>
          {icon}
          <h3 className="text-sm font-semibold">{title}</h3>
          <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">{items.length}</span>
        </div>
        <div className="space-y-2">
          {items.map((task) => (
            <div key={task.id}
              onClick={() => onTaskClick(task)}
              className="flex items-center gap-3 bg-white rounded-md px-4 py-3 border border-gray-100 cursor-pointer hover:border-gray-300 transition-colors">
              <button
                onClick={(e) => { e.stopPropagation(); onToggleDone(task); }}
                className={`w-4 h-4 rounded border-2 shrink-0 flex items-center justify-center transition-colors ${
                  task.status === 'done' ? 'bg-gray-900 border-gray-900 text-white' : 'border-gray-300 hover:border-gray-500'
                }`}>
                {task.status === 'done' && <CheckSquare className="w-3 h-3" />}
              </button>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium truncate ${task.status === 'done' ? 'line-through text-gray-400' : 'text-gray-900'}`}>
                  {task.title}
                </p>
                <div className="flex gap-2 text-xs text-gray-400 mt-0.5">
                  {task.assignee_name && <span>{task.assignee_name}</span>}
                  {task.project_name && <span className="text-blue-500">{task.project_name}</span>}
                  {task.due_date && <span>{formatDate(task.due_date)}</span>}
                </div>
              </div>
              <span className="text-xs px-1.5 py-0.5 rounded-md border border-gray-200 text-gray-500 font-medium">
                {PRIORITY_LABEL[task.priority]}
              </span>
              {task.estimated_minutes != null && (
                <span className="text-xs text-gray-400 flex items-center gap-0.5">
                  <Clock className="w-3 h-3" />{task.estimated_minutes}分
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    ) : null
  );

  return (
    <div className="max-w-3xl mx-auto">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <div className="bg-white rounded-md p-4 border border-gray-100">
          <p className="text-xs text-gray-500">期限超過</p>
          <p className={`text-2xl font-bold ${overdue.length > 0 ? 'text-red-600' : 'text-gray-300'}`}>{overdue.length}</p>
        </div>
        <div className="bg-white rounded-md p-4 border border-gray-100">
          <p className="text-xs text-gray-500">今日の期限</p>
          <p className="text-2xl font-bold text-gray-900">{todayTasks.length}</p>
        </div>
        <div className="bg-white rounded-md p-4 border border-gray-100">
          <p className="text-xs text-gray-500">進行中</p>
          <p className="text-2xl font-bold text-gray-900">{inProgress.length}</p>
        </div>
        <div className="bg-white rounded-md p-4 border border-gray-100">
          <p className="text-xs text-gray-500">残り工数</p>
          <p className="text-2xl font-bold text-gray-900">{totalEstimated > 0 ? `${Math.round(totalEstimated / 60)}h` : '-'}</p>
        </div>
      </div>

      <Section title="期限超過" icon={<AlertCircle className="w-4 h-4" />} color="text-red-600" items={overdue} />
      <Section title="今日の期限" icon={<Bell className="w-4 h-4" />} color="text-gray-900" items={todayTasks} />
      <Section title="進行中" icon={<Clock className="w-4 h-4" />} color="text-gray-700" items={inProgress} />
      <Section title="今日完了" icon={<CheckSquare className="w-4 h-4" />} color="text-green-600" items={recentlyDone} />

      {overdue.length === 0 && todayTasks.length === 0 && inProgress.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <CheckSquare className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-sm">今日のタスクはありません</p>
        </div>
      )}
    </div>
  );
}
