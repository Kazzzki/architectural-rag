'use client';

import React from 'react';
import { AlertCircle, Clock, Bell, CheckSquare } from 'lucide-react';
import type { Task } from './types';
import { PRIORITY_LABEL, formatDate } from './types';
import SwipeableTaskCard from './SwipeableTaskCard';

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
        <div className="space-y-1">
          {items.map((task) => (
            <SwipeableTaskCard
              key={task.id}
              task={task}
              onClick={() => onTaskClick(task)}
              onComplete={() => onToggleDone(task)}
            />
          ))}
        </div>
      </div>
    ) : null
  );

  return (
    <div className="max-w-3xl mx-auto">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 mb-4 sm:mb-6">
        <div className="bg-white rounded-md p-3 sm:p-4 border border-gray-100">
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
