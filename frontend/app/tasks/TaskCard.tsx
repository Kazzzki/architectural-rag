'use client';

import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Calendar, Clock, Bell, CheckSquare } from 'lucide-react';
import type { Task } from './types';
import { PRIORITY_LABEL, PRIORITY_COLOR, formatDate } from './types';

export default function TaskCard({
  task,
  onClick,
  onToggleDone,
  overlay = false,
}: {
  task: Task;
  onClick?: () => void;
  onToggleDone?: () => void;
  overlay?: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const labels = task.label_names?.split(',').filter(Boolean) ?? [];
  const labelColors = task.label_colors?.split(',').filter(Boolean) ?? [];

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={`bg-white rounded-md px-3 py-2.5 sm:px-4 sm:py-3 border border-gray-100 cursor-pointer
        hover:border-gray-300 transition-colors select-none
        ${isDragging && !overlay ? 'opacity-30' : ''}
        ${overlay ? 'shadow-lg rotate-1 border-gray-300' : ''}
      `}
    >
      <div className="flex items-start gap-2 mb-2">
        <button
          onClick={(e) => { e.stopPropagation(); onToggleDone?.(); }}
          aria-label={task.status === 'done' ? '未完了にする' : '完了にする'}
          className={`mt-0.5 w-6 h-6 rounded-full border-2 shrink-0 flex items-center justify-center transition-colors ${
            task.status === 'done' ? 'bg-green-500 border-green-500 text-white' : 'border-gray-300 hover:border-gray-500'
          }`}
        >
          {task.status === 'done' && <CheckSquare className="w-3 h-3" />}
        </button>
        <span className={`flex-1 text-sm font-medium leading-snug line-clamp-2 ${task.status === 'done' ? 'line-through text-gray-400' : 'text-gray-900'}`}>
          {task.title}
        </span>
        <span className={`text-xs px-1.5 py-0.5 rounded-md border flex-shrink-0 font-medium ${PRIORITY_COLOR[task.priority]}`}>
          {PRIORITY_LABEL[task.priority]}
        </span>
      </div>

      {/* Progress bar for parent tasks */}
      {task.progress != null && task.progress > 0 && (
        <div className="mb-2">
          <div className="w-full bg-gray-100 rounded-full h-1.5">
            <div className="bg-gray-600 h-1.5 rounded-full transition-all" style={{ width: `${task.progress}%` }} />
          </div>
        </div>
      )}

      {/* Labels */}
      {labels.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {labels.map((name, i) => (
            <span key={i} className="text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium"
              style={{ backgroundColor: labelColors[i] || '#6366f1' }}>
              {name}
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 items-center text-xs text-gray-400">
        {task.assignee_name && (
          <span className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-md text-[11px]">
            {task.assignee_name}
          </span>
        )}
        {task.project_name && (
          <span className="text-blue-500 font-medium">{task.project_name}</span>
        )}
        {task.category_name && (
          <span>{task.category_name}</span>
        )}
        {task.due_date && (() => {
          const isOverdue = task.due_date!.slice(0, 10) < new Date().toISOString().slice(0, 10) && task.status !== 'done';
          return (
            <span className={`flex items-center gap-0.5 ${isOverdue ? 'text-gray-900 font-semibold' : ''}`}>
              <Calendar className="w-3 h-3" />
              {isOverdue && <span>!</span>}
              {formatDate(task.due_date)}
            </span>
          );
        })()}
        {task.estimated_minutes != null && (
          <span className="flex items-center gap-0.5">
            <Clock className="w-3 h-3" />
            {task.estimated_minutes}分
          </span>
        )}
        {task.milestone_name && (
          <span className="text-purple-500 text-[11px]">◆ {task.milestone_name}</span>
        )}
        {task.has_today_reminder === 1 && (
          <span title="本日リマインダーあり">
            <Bell className="w-3 h-3 text-gray-400" />
          </span>
        )}
      </div>
    </div>
  );
}
