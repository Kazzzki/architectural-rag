'use client';

import React, { useState, useMemo } from 'react';
import { CheckSquare, ArrowUpDown } from 'lucide-react';
import type { Task } from './types';
import { PRIORITY_LABEL, STATUS_LABEL, formatDate } from './types';
import { api } from './taskApi';

type SortKey = 'title' | 'priority' | 'status' | 'due_date' | 'assignee_name' | 'project_name' | 'estimated_minutes';

export default function TaskTable({
  tasks,
  onTaskClick,
  onToggleDone,
  onRefresh,
}: {
  tasks: Task[];
  onTaskClick: (task: Task) => void;
  onToggleDone: (task: Task) => void;
  onRefresh: () => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>('due_date');
  const [sortAsc, setSortAsc] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkAction, setBulkAction] = useState('');

  const sorted = useMemo(() => {
    const priorityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
    const statusOrder: Record<string, number> = { todo: 0, in_progress: 1, done: 2 };
    return [...tasks].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case 'title': cmp = a.title.localeCompare(b.title); break;
        case 'priority': cmp = (priorityOrder[a.priority] ?? 1) - (priorityOrder[b.priority] ?? 1); break;
        case 'status': cmp = (statusOrder[a.status] ?? 0) - (statusOrder[b.status] ?? 0); break;
        case 'due_date': cmp = (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999'); break;
        case 'assignee_name': cmp = (a.assignee_name ?? '').localeCompare(b.assignee_name ?? ''); break;
        case 'project_name': cmp = (a.project_name ?? '').localeCompare(b.project_name ?? ''); break;
        case 'estimated_minutes': cmp = (a.estimated_minutes ?? 0) - (b.estimated_minutes ?? 0); break;
      }
      return sortAsc ? cmp : -cmp;
    });
  }, [tasks, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(true); }
  };

  const toggleAll = () => {
    if (selected.size === tasks.length) setSelected(new Set());
    else setSelected(new Set(tasks.map((t) => t.id)));
  };

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleBulk = async () => {
    if (!bulkAction || selected.size === 0) return;
    const ids = Array.from(selected);
    if (bulkAction === 'delete') {
      if (!confirm(`${ids.length}件のタスクを削除しますか？`)) return;
      for (const id of ids) await api.deleteTask(id);
    } else if (['todo', 'in_progress', 'done'].includes(bulkAction)) {
      await api.bulkUpdate({ task_ids: ids, status: bulkAction });
    } else if (['high', 'medium', 'low'].includes(bulkAction)) {
      await api.bulkUpdate({ task_ids: ids, priority: bulkAction });
    }
    setSelected(new Set());
    setBulkAction('');
    onRefresh();
  };

  const Th = ({ label, k }: { label: string; k: SortKey }) => (
    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 cursor-pointer hover:text-gray-700 whitespace-nowrap"
      onClick={() => toggleSort(k)}>
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown className={`w-3 h-3 ${sortKey === k ? 'text-gray-900' : 'text-gray-300'}`} />
      </span>
    </th>
  );

  return (
    <div className="max-w-7xl mx-auto">
      {/* Bulk actions */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 mb-3 p-3 bg-gray-100 rounded-md">
          <span className="text-sm text-gray-700">{selected.size}件選択中</span>
          <select value={bulkAction} onChange={(e) => setBulkAction(e.target.value)}
            className="px-2 py-1 rounded border border-gray-300 text-sm bg-white">
            <option value="">操作を選択...</option>
            <optgroup label="ステータス変更">
              <option value="todo">→ ToDo</option>
              <option value="in_progress">→ 進行中</option>
              <option value="done">→ 完了</option>
            </optgroup>
            <optgroup label="優先度変更">
              <option value="high">→ 高</option>
              <option value="medium">→ 中</option>
              <option value="low">→ 低</option>
            </optgroup>
            <option value="delete">削除</option>
          </select>
          <button onClick={handleBulk} disabled={!bulkAction}
            className="px-3 py-1 bg-gray-900 text-white text-sm rounded hover:bg-gray-700 disabled:opacity-50">
            実行
          </button>
          <button onClick={() => setSelected(new Set())} className="text-sm text-gray-500 hover:text-gray-700">
            選択解除
          </button>
        </div>
      )}

      <div className="overflow-x-auto bg-white rounded-md border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 w-8">
                <input type="checkbox" checked={selected.size === tasks.length && tasks.length > 0}
                  onChange={toggleAll} className="rounded border-gray-300" />
              </th>
              <Th label="タイトル" k="title" />
              <Th label="担当者" k="assignee_name" />
              <Th label="優先度" k="priority" />
              <Th label="ステータス" k="status" />
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">ラベル</th>
              <Th label="期限" k="due_date" />
              <Th label="PJ" k="project_name" />
              <Th label="工数" k="estimated_minutes" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((task) => {
              const isOverdue = task.due_date && task.due_date.slice(0, 10) < new Date().toISOString().slice(0, 10) && task.status !== 'done';
              const labels = task.label_names?.split(',').filter(Boolean) ?? [];
              const labelColors = task.label_colors?.split(',').filter(Boolean) ?? [];
              return (
                <tr key={task.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => onTaskClick(task)}>
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(task.id)}
                      onChange={() => toggle(task.id)} className="rounded border-gray-300" />
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <button onClick={(e) => { e.stopPropagation(); onToggleDone(task); }}
                        className={`w-4 h-4 rounded border-2 shrink-0 flex items-center justify-center ${
                          task.status === 'done' ? 'bg-gray-900 border-gray-900 text-white' : 'border-gray-300'
                        }`}>
                        {task.status === 'done' && <CheckSquare className="w-3 h-3" />}
                      </button>
                      <span className={`${task.status === 'done' ? 'line-through text-gray-400' : 'text-gray-900'} truncate max-w-[200px]`}>
                        {task.title}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-gray-600 text-xs">{task.assignee_name ?? '-'}</td>
                  <td className="px-3 py-2">
                    <span className="text-xs px-1.5 py-0.5 rounded border border-gray-200">{PRIORITY_LABEL[task.priority]}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-xs text-gray-600">{STATUS_LABEL[task.status]}</span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      {labels.map((name, i) => (
                        <span key={i} className="text-[10px] px-1.5 py-0.5 rounded-full text-white"
                          style={{ backgroundColor: labelColors[i] || '#6366f1' }}>{name}</span>
                      ))}
                    </div>
                  </td>
                  <td className={`px-3 py-2 text-xs ${isOverdue ? 'text-red-600 font-semibold' : 'text-gray-600'}`}>
                    {isOverdue && '! '}{formatDate(task.due_date)}
                  </td>
                  <td className="px-3 py-2 text-xs text-blue-500">{task.project_name ?? ''}</td>
                  <td className="px-3 py-2 text-xs text-gray-500">
                    {task.estimated_minutes ? `${task.estimated_minutes}分` : ''}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {tasks.length === 0 && (
          <div className="text-center py-12 text-gray-400 text-sm">タスクがありません</div>
        )}
      </div>
    </div>
  );
}
