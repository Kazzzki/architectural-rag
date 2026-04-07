'use client';

import React, { useRef, useState } from 'react';
import { Check, Calendar } from 'lucide-react';
import type { Task } from './types';
import { PRIORITY_LABEL, formatDate } from './types';

const SWIPE_THRESHOLD = 80;

export default function SwipeableTaskCard({
  task,
  onClick,
  onComplete,
  onSchedule,
  disabled = false,
}: {
  task: Task;
  onClick: () => void;
  onComplete: () => void;
  onSchedule?: () => void;
  disabled?: boolean;
}) {
  const startX = useRef(0);
  const currentX = useRef(0);
  const cardRef = useRef<HTMLDivElement>(null);
  const [swiping, setSwiping] = useState(false);

  const handleTouchStart = (e: React.TouchEvent) => {
    if (disabled) return;
    startX.current = e.touches[0].clientX;
    currentX.current = 0;
    setSwiping(true);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!swiping || disabled) return;
    const diff = e.touches[0].clientX - startX.current;
    currentX.current = diff;
    if (cardRef.current) {
      const clamped = Math.max(-120, Math.min(120, diff));
      cardRef.current.style.transform = `translateX(${clamped}px)`;
      cardRef.current.style.transition = 'none';
    }
  };

  const handleTouchEnd = () => {
    if (!swiping || disabled) return;
    setSwiping(false);
    const diff = currentX.current;

    if (cardRef.current) {
      cardRef.current.style.transition = 'transform 200ms ease-out';
      cardRef.current.style.transform = 'translateX(0)';
    }

    if (diff > SWIPE_THRESHOLD) {
      // Right swipe: complete
      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        navigator.vibrate(10);
      }
      onComplete();
    } else if (diff < -SWIPE_THRESHOLD && onSchedule) {
      // Left swipe: schedule
      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        navigator.vibrate(10);
      }
      onSchedule();
    }
  };

  const labels = task.label_names?.split(',').filter(Boolean) ?? [];
  const labelColors = task.label_colors?.split(',').filter(Boolean) ?? [];
  const isOverdue = task.due_date && task.due_date.slice(0, 10) < new Date().toISOString().slice(0, 10) && task.status !== 'done';

  return (
    <div className="relative overflow-hidden rounded-lg">
      {/* Swipe backgrounds */}
      <div className="absolute inset-0 flex">
        <div className="flex-1 bg-green-500 flex items-center pl-4">
          <Check className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1 bg-blue-500 flex items-center justify-end pr-4">
          <Calendar className="w-5 h-5 text-white" />
        </div>
      </div>

      {/* Card */}
      <div ref={cardRef}
        className="relative bg-white px-3 py-2.5 cursor-pointer active:bg-gray-50 z-10"
        onClick={onClick}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <div className="flex items-center gap-2.5">
          <button
            onClick={(e) => { e.stopPropagation(); onComplete(); }}
            aria-label={task.status === 'done' ? '未完了にする' : '完了にする'}
            className={`w-6 h-6 rounded-full border-2 shrink-0 flex items-center justify-center transition-colors ${
              task.status === 'done' ? 'bg-green-500 border-green-500 text-white' : 'border-gray-300 hover:border-gray-500'
            }`}>
            {task.status === 'done' && <Check className="w-3.5 h-3.5" />}
          </button>

          <div className="flex-1 min-w-0">
            <p className={`text-sm leading-tight ${task.status === 'done' ? 'line-through text-gray-400' : 'text-gray-900'}`}>
              {task.title}
            </p>
            <div className="flex items-center gap-2 mt-0.5">
              {task.assignee_name && (
                <span className="text-[11px] text-gray-500">{task.assignee_name}</span>
              )}
              {task.project_name && (
                <span className="text-[11px] text-blue-500">{task.project_name}</span>
              )}
              {labels.length > 0 && labels.slice(0, 2).map((name, i) => (
                <span key={i} className="text-[9px] px-1 py-0.5 rounded-full text-white"
                  style={{ backgroundColor: labelColors[i] || '#6366f1' }}>{name}</span>
              ))}
            </div>
          </div>

          <div className="flex flex-col items-end gap-0.5 shrink-0">
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-gray-200 text-gray-500 font-medium">
              {PRIORITY_LABEL[task.priority]}
            </span>
            {task.due_date && (
              <span className={`text-[10px] ${isOverdue ? 'text-red-600 font-semibold' : 'text-gray-400'}`}>
                {isOverdue && '! '}{formatDate(task.due_date)}
              </span>
            )}
          </div>
        </div>

        {/* Progress bar for parent tasks */}
        {task.progress != null && task.progress > 0 && (
          <div className="mt-1.5 w-full bg-gray-100 rounded-full h-1">
            <div className="bg-gray-500 h-1 rounded-full" style={{ width: `${task.progress}%` }} />
          </div>
        )}
      </div>
    </div>
  );
}
