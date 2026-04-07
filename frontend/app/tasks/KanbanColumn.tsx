'use client';

import React from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import TaskCard from './TaskCard';
import type { Task } from './types';
import { STATUS_LABEL, STATUS_HEADER_COLOR } from './types';

export default function KanbanColumn({
  status,
  tasks,
  onTaskClick,
  onToggleDone,
}: {
  status: string;
  tasks: Task[];
  onTaskClick: (task: Task) => void;
  onToggleDone?: (task: Task) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const ids = tasks.map((t) => t.id);

  return (
    <div
      ref={setNodeRef}
      className={`flex-1 min-w-0 md:min-w-[240px] flex flex-col rounded-md transition-colors
        ${isOver ? 'bg-gray-100 ring-1 ring-gray-200' : 'bg-gray-50'}
      `}
    >
      <div className={`px-4 py-3 rounded-t-md flex items-center gap-2 ${STATUS_HEADER_COLOR[status]}`}>
        <span className="font-semibold text-sm">{STATUS_LABEL[status]}</span>
        <span className="ml-auto bg-gray-200 text-gray-600 text-xs px-2 py-0.5 rounded-full font-medium">
          {tasks.length}
        </span>
      </div>
      <div className="flex-1 p-3 flex flex-col gap-2 min-h-[120px]">
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} onClick={() => onTaskClick(task)} onToggleDone={() => onToggleDone?.(task)} />
          ))}
        </SortableContext>
      </div>
    </div>
  );
}
