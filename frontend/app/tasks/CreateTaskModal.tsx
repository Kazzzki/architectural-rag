'use client';

import React, { useState } from 'react';
import { X } from 'lucide-react';
import type { Task, Category, Label, Milestone } from './types';
import { api } from './taskApi';

export default function CreateTaskModal({
  categories,
  projects,
  labels,
  milestones,
  defaultProject,
  onClose,
  onCreate,
}: {
  categories: Category[];
  projects: string[];
  labels: Label[];
  milestones: Milestone[];
  defaultProject: string;
  onClose: () => void;
  onCreate: (task: Task) => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<Task['status']>('todo');
  const [priority, setPriority] = useState<Task['priority']>('medium');
  const [categoryId, setCategoryId] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [estimated, setEstimated] = useState('');
  const [projectName, setProjectName] = useState(defaultProject);
  const [assigneeName, setAssigneeName] = useState('');
  const [milestoneId, setMilestoneId] = useState('');
  const [selectedLabels, setSelectedLabels] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setLoading(true);
    try {
      const task = await api.createTask({
        title: title.trim(),
        description: description || undefined,
        status,
        priority,
        category_id: categoryId ? parseInt(categoryId) : undefined,
        due_date: dueDate || undefined,
        estimated_minutes: estimated ? parseInt(estimated) : undefined,
        project_name: projectName || undefined,
        assignee_name: assigneeName || undefined,
        milestone_id: milestoneId ? parseInt(milestoneId) : undefined,
      });
      if (selectedLabels.length > 0) {
        await api.attachLabels(task.id, selectedLabels);
      }
      onCreate(task);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : '作成に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  const toggleLabel = (id: number) => {
    setSelectedLabels((prev) =>
      prev.includes(id) ? prev.filter((l) => l !== id) : [...prev, id]
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white shadow-lg w-full sm:max-w-md max-h-full sm:max-h-[90vh] sm:rounded-md overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 sticky top-0 bg-white">
          <h2 className="text-lg font-semibold text-gray-900">新しいタスク</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-500">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">タイトル *</label>
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="タスクのタイトルを入力..."
              className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 focus:border-transparent"
              autoFocus />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">説明</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="詳細説明（任意）" rows={3}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 focus:border-transparent resize-none" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ステータス</label>
              <select value={status} onChange={(e) => setStatus(e.target.value as Task['status'])}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm bg-white">
                <option value="todo">ToDo</option>
                <option value="in_progress">進行中</option>
                <option value="done">完了</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">優先度</label>
              <select value={priority} onChange={(e) => setPriority(e.target.value as Task['priority'])}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm bg-white">
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">プロジェクト</label>
              <select value={projectName} onChange={(e) => setProjectName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm bg-white">
                <option value="">なし</option>
                {projects.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">担当者</label>
              <input type="text" value={assigneeName} onChange={(e) => setAssigneeName(e.target.value)}
                placeholder="担当者名"
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm" />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">カテゴリ</label>
              <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm bg-white">
                <option value="">なし</option>
                {categories.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">期限</label>
              <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm" />
            </div>
          </div>

          {milestones.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">マイルストーン</label>
              <select value={milestoneId} onChange={(e) => setMilestoneId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm bg-white">
                <option value="">なし</option>
                {milestones.map((m) => <option key={m.id} value={String(m.id)}>{m.name}</option>)}
              </select>
            </div>
          )}

          {labels.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ラベル</label>
              <div className="flex flex-wrap gap-1.5">
                {labels.map((l) => (
                  <button key={l.id} type="button" onClick={() => toggleLabel(l.id)}
                    className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                      selectedLabels.includes(l.id)
                        ? 'text-white border-transparent'
                        : 'text-gray-600 border-gray-200 hover:border-gray-400'
                    }`}
                    style={selectedLabels.includes(l.id) ? { backgroundColor: l.color } : {}}>
                    {l.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">予想時間（分）</label>
            <input type="number" value={estimated} onChange={(e) => setEstimated(e.target.value)}
              placeholder="例: 60" min="1"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm" />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50 transition-colors">
              キャンセル
            </button>
            <button type="submit" disabled={!title.trim() || loading}
              className="flex-1 py-2 rounded-lg bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-50 transition-colors">
              {loading ? '作成中...' : '作成'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
