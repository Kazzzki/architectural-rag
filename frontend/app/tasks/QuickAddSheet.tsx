'use client';

import React, { useState } from 'react';
import { Drawer } from 'vaul';
import { Calendar, ChevronDown, Loader2 } from 'lucide-react';
import { api } from './taskApi';
import type { Task } from './types';

export default function QuickAddSheet({
  open,
  onOpenChange,
  onCreated,
  defaultProject,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (task: Task) => void;
  defaultProject?: string;
}) {
  const [title, setTitle] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [showDetails, setShowDetails] = useState(false);
  const [priority, setPriority] = useState<'low' | 'medium' | 'high'>('medium');
  const [assignee, setAssignee] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);

  const today = new Date().toISOString().slice(0, 10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const nextWeek = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);

  const handleCreate = async () => {
    if (!title.trim() || loading) return;
    setLoading(true);
    try {
      const task = await api.createTask({
        title: title.trim(),
        due_date: dueDate || undefined,
        priority,
        assignee_name: assignee || undefined,
        description: description || undefined,
        project_name: defaultProject || undefined,
        status: 'todo',
      });
      onCreated(task);
      setTitle('');
      setDueDate('');
      setPriority('medium');
      setAssignee('');
      setDescription('');
      setShowDetails(false);
      onOpenChange(false);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange}>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 bg-black/40 z-50" />
        <Drawer.Content className="fixed bottom-0 inset-x-0 z-50 bg-white rounded-t-2xl focus:outline-none">
          <div className="mx-auto w-12 h-1.5 bg-gray-300 rounded-full mt-3 mb-2" />

          <div className="px-4 pb-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
            <Drawer.Title className="text-base font-semibold text-gray-900 mb-3">
              タスクを追加
            </Drawer.Title>

            {/* Title input */}
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="タスクのタイトルを入力..."
              className="w-full px-3 py-3 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 mb-3"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  handleCreate();
                }
              }}
            />

            {/* Quick date buttons */}
            <div className="flex gap-2 mb-3">
              {[
                { label: '今日', value: today },
                { label: '明日', value: tomorrow },
                { label: '来週', value: nextWeek },
              ].map(({ label, value }) => (
                <button key={value}
                  onClick={() => setDueDate(dueDate === value ? '' : value)}
                  className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                    dueDate === value
                      ? 'bg-gray-900 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}>
                  {label}
                </button>
              ))}
              <div className="relative">
                <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)}
                  className="opacity-0 absolute inset-0 w-full h-full cursor-pointer" />
                <button className="px-3 py-2 rounded-lg text-xs font-medium bg-gray-100 text-gray-600 flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5" />日付
                </button>
              </div>
            </div>

            {/* Expandable details */}
            <button onClick={() => setShowDetails(!showDetails)}
              className="flex items-center gap-1 text-xs text-gray-500 mb-3 hover:text-gray-700">
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showDetails ? 'rotate-180' : ''}`} />
              {showDetails ? '詳細を閉じる' : '詳細を追加'}
            </button>

            {showDetails && (
              <div className="space-y-3 mb-3">
                <div className="flex gap-2">
                  <select value={priority} onChange={(e) => setPriority(e.target.value as 'low' | 'medium' | 'high')}
                    className="flex-1 px-3 py-2 rounded-lg border border-gray-200 text-sm bg-white">
                    <option value="high">高優先度</option>
                    <option value="medium">中優先度</option>
                    <option value="low">低優先度</option>
                  </select>
                  <input type="text" value={assignee} onChange={(e) => setAssignee(e.target.value)}
                    placeholder="担当者"
                    className="flex-1 px-3 py-2 rounded-lg border border-gray-200 text-sm" />
                </div>
                <textarea value={description} onChange={(e) => setDescription(e.target.value)}
                  placeholder="説明（任意）" rows={2}
                  className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm resize-none" />
              </div>
            )}

            {/* Create button */}
            <button onClick={handleCreate}
              disabled={!title.trim() || loading}
              className="w-full py-3 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              {loading ? '作成中...' : '作成'}
            </button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
