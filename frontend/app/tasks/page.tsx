'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '@/lib/api';
import {
  DndContext,
  DragEndEvent,
  DragOverEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useDroppable } from '@dnd-kit/core';
import {
  Plus,
  X,
  Send,
  Bell,
  Trash2,
  MessageSquare,
  Loader2,
  Bot,
} from 'lucide-react';

// ===== 型定義 =====

interface Category {
  id: number;
  name: string;
  color: string;
}

interface Comment {
  id: number;
  task_id: number;
  content: string;
  created_at: string;
}

interface Reminder {
  id: number;
  task_id: number;
  remind_at: string;
  message?: string;
  is_sent: number;
}

interface Task {
  id: number;
  title: string;
  description?: string;
  status: 'todo' | 'in_progress' | 'done';
  priority: 'low' | 'medium' | 'high';
  category_id?: number;
  category_name?: string;
  category_color?: string;
  due_date?: string;
  estimated_minutes?: number;
  actual_minutes?: number;
  created_at: string;
  updated_at: string;
  comments?: Comment[];
  reminders?: Reminder[];
}

interface ChatMessage {
  role: 'user' | 'ai';
  content: string;
}

// ===== API クライアント =====

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await authFetch(path, {
    ...opts,
    signal: AbortSignal.timeout(15000),
    headers: { 'Content-Type': 'application/json', ...(opts?.headers ?? {}) },
  });
  if (res.status === 204) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

const api = {
  getTasks: (filters: Record<string, string> = {}) => {
    const q = new URLSearchParams(filters).toString();
    return apiFetch(`/api/tasks${q ? `?${q}` : ''}`);
  },
  createTask: (data: Partial<Task>) =>
    apiFetch('/api/tasks', { method: 'POST', body: JSON.stringify(data) }),
  getTask: (id: number) => apiFetch(`/api/tasks/${id}`),
  updateTask: (id: number, data: Partial<Task>) =>
    apiFetch(`/api/tasks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTask: (id: number) =>
    apiFetch(`/api/tasks/${id}`, { method: 'DELETE' }),
  getCategories: () => apiFetch('/api/task-categories'),
  createCategory: (data: { name: string; color: string }) =>
    apiFetch('/api/task-categories', { method: 'POST', body: JSON.stringify(data) }),
  addComment: (taskId: number, content: string) =>
    apiFetch(`/api/tasks/${taskId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
  addReminder: (taskId: number, remind_at: string, message?: string) =>
    apiFetch(`/api/tasks/${taskId}/reminders`, {
      method: 'POST',
      body: JSON.stringify({ remind_at, message }),
    }),
  getPendingReminders: () => apiFetch('/api/tasks/reminders/pending'),
  chat: (message: string) =>
    apiFetch('/api/tasks/chat', { method: 'POST', body: JSON.stringify({ message }) }),
};

// ===== ユーティリティ =====

const PRIORITY_LABEL: Record<string, string> = { high: 'H', medium: 'M', low: 'L' };
const STATUS_LABEL: Record<string, string> = {
  todo: 'Todo',
  in_progress: '進行中',
  done: '完了',
};

function formatDate(iso?: string) {
  if (!iso) return '';
  return iso.slice(0, 10);
}

// ===== タスクカード（sortable） =====

function TaskCard({
  task,
  onClick,
  overlay = false,
}: {
  task: Task;
  onClick?: () => void;
  overlay?: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={`bg-white rounded-md px-3 py-2.5 border border-gray-200 cursor-pointer
        hover:border-gray-300 transition-colors select-none
        ${isDragging && !overlay ? 'opacity-30' : ''}
        ${overlay ? 'border-gray-300' : ''}
      `}
    >
      <div className="flex items-start gap-2">
        <span className={`flex-1 text-sm font-medium leading-snug line-clamp-2 ${task.status === 'done' ? 'line-through text-gray-400' : 'text-gray-900'}`}>
          {task.title}
        </span>
        <span className="text-xs font-medium text-gray-400 flex-shrink-0 mt-0.5">
          {PRIORITY_LABEL[task.priority]}
        </span>
      </div>

      {(task.category_name || task.due_date) && (
        <div className="flex flex-wrap gap-2 items-center text-xs text-gray-400 mt-1.5">
          {task.category_name && (
            <span>{task.category_name}</span>
          )}
          {task.due_date && (
            <span>{formatDate(task.due_date)}</span>
          )}
        </div>
      )}
    </div>
  );
}

// ===== カンバン列 =====

function KanbanColumn({
  status,
  tasks,
  onTaskClick,
}: {
  status: string;
  tasks: Task[];
  onTaskClick: (task: Task) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const ids = tasks.map((t) => t.id);

  return (
    <div
      ref={setNodeRef}
      className={`flex-1 min-w-0 md:min-w-[240px] flex flex-col rounded-md transition-colors
        ${isOver ? 'bg-gray-100 ring-1 ring-gray-300' : 'bg-gray-50'}
      `}
    >
      {/* ヘッダー */}
      <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-2">
        <span className="font-medium text-sm text-gray-900">{STATUS_LABEL[status]}</span>
        <span className="ml-auto bg-gray-200 text-gray-600 text-xs px-2 py-0.5 rounded-md font-medium">
          {tasks.length}
        </span>
      </div>

      {/* タスクリスト */}
      <div className="flex-1 p-3 flex flex-col gap-1.5 min-h-[120px]">
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} onClick={() => onTaskClick(task)} />
          ))}
        </SortableContext>
      </div>
    </div>
  );
}

// ===== タスク作成モーダル =====

function CreateTaskModal({
  categories,
  onClose,
  onCreate,
}: {
  categories: Category[];
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
  const [loading, setLoading] = useState(false);

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
      });
      onCreate(task);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-md shadow-lg w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">新しいタスク</h2>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-gray-100 text-gray-500">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">タイトル *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="タスクのタイトルを入力..."
              className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">説明</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="詳細説明（任意）"
              rows={3}
              className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400 resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ステータス</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as Task['status'])}
                className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400 bg-white"
              >
                <option value="todo">ToDo</option>
                <option value="in_progress">進行中</option>
                <option value="done">完了</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">優先度</label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as Task['priority'])}
                className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400 bg-white"
              >
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">カテゴリ</label>
              <select
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400 bg-white"
              >
                <option value="">なし</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">期限</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              予想時間（分）
            </label>
            <input
              type="number"
              value={estimated}
              onChange={(e) => setEstimated(e.target.value)}
              placeholder="例: 60"
              min="1"
              className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 rounded-md border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              キャンセル
            </button>
            <button
              type="submit"
              disabled={!title.trim() || loading}
              className="flex-1 py-2 rounded-md bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? '作成中...' : '作成'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ===== タスク詳細サイドパネル =====

function TaskDetailPanel({
  taskId,
  categories,
  onClose,
  onUpdate,
  onDelete,
}: {
  taskId: number;
  categories: Category[];
  onClose: () => void;
  onUpdate: (task: Task) => void;
  onDelete: (id: number) => void;
}) {
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // 編集フィールド
  const [editTitle, setEditTitle] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editStatus, setEditStatus] = useState<Task['status']>('todo');
  const [editPriority, setEditPriority] = useState<Task['priority']>('medium');
  const [editCategory, setEditCategory] = useState('');
  const [editDueDate, setEditDueDate] = useState('');
  const [editEstimated, setEditEstimated] = useState('');
  const [editActual, setEditActual] = useState('');

  // コメント
  const [newComment, setNewComment] = useState('');
  const [addingComment, setAddingComment] = useState(false);

  // リマインダー
  const [newReminderAt, setNewReminderAt] = useState('');
  const [newReminderMsg, setNewReminderMsg] = useState('');
  const [addingReminder, setAddingReminder] = useState(false);

  const loadTask = useCallback(async () => {
    setLoading(true);
    try {
      const t: Task = await api.getTask(taskId);
      setTask(t);
      setEditTitle(t.title);
      setEditDesc(t.description ?? '');
      setEditStatus(t.status);
      setEditPriority(t.priority);
      setEditCategory(t.category_id?.toString() ?? '');
      setEditDueDate(t.due_date ?? '');
      setEditEstimated(t.estimated_minutes?.toString() ?? '');
      setEditActual(t.actual_minutes?.toString() ?? '');
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    loadTask();
  }, [loadTask]);

  const handleSave = async () => {
    if (!task) return;
    setSaving(true);
    try {
      const updated: Task = await api.updateTask(task.id, {
        title: editTitle,
        description: editDesc || undefined,
        status: editStatus,
        priority: editPriority,
        category_id: editCategory ? parseInt(editCategory) : undefined,
        due_date: editDueDate || undefined,
        estimated_minutes: editEstimated ? parseInt(editEstimated) : undefined,
        actual_minutes: editActual ? parseInt(editActual) : undefined,
      });
      onUpdate(updated);
      setTask({ ...updated, comments: task.comments, reminders: task.reminders });
    } finally {
      setSaving(false);
    }
  };

  const handleAddComment = async () => {
    if (!task || !newComment.trim()) return;
    setAddingComment(true);
    try {
      const comment: Comment = await api.addComment(task.id, newComment.trim());
      setTask((prev) => prev ? { ...prev, comments: [...(prev.comments ?? []), comment] } : prev);
      setNewComment('');
    } finally {
      setAddingComment(false);
    }
  };

  const handleAddReminder = async () => {
    if (!task || !newReminderAt) return;
    setAddingReminder(true);
    try {
      const reminder: Reminder = await api.addReminder(task.id, newReminderAt, newReminderMsg || undefined);
      setTask((prev) => prev ? { ...prev, reminders: [...(prev.reminders ?? []), reminder] } : prev);
      setNewReminderAt('');
      setNewReminderMsg('');
    } finally {
      setAddingReminder(false);
    }
  };

  const handleDelete = async () => {
    if (!task) return;
    if (!confirm(`「${task.title}」を削除しますか？`)) return;
    await api.deleteTask(task.id);
    onDelete(task.id);
  };

  return (
    <div className="w-full md:w-96 flex-shrink-0 h-full border-l border-gray-200 bg-white flex flex-col">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <h3 className="text-sm font-semibold text-gray-700">タスク詳細</h3>
        <div className="flex gap-2">
          <button
            onClick={handleDelete}
            className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            title="削除"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : !task ? (
        <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
          読み込みエラー
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* タイトル */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">タイトル</label>
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
            />
          </div>

          {/* 説明 */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">説明</label>
            <textarea
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400 resize-none"
            />
          </div>

          {/* ステータス・優先度 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">ステータス</label>
              <select
                value={editStatus}
                onChange={(e) => setEditStatus(e.target.value as Task['status'])}
                className="w-full px-2 py-1.5 rounded-md border border-gray-200 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
              >
                <option value="todo">ToDo</option>
                <option value="in_progress">進行中</option>
                <option value="done">完了</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">優先度</label>
              <select
                value={editPriority}
                onChange={(e) => setEditPriority(e.target.value as Task['priority'])}
                className="w-full px-2 py-1.5 rounded-md border border-gray-200 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
              >
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
          </div>

          {/* カテゴリ・期限 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">カテゴリ</label>
              <select
                value={editCategory}
                onChange={(e) => setEditCategory(e.target.value)}
                className="w-full px-2 py-1.5 rounded-md border border-gray-200 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
              >
                <option value="">なし</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">期限</label>
              <input
                type="date"
                value={editDueDate}
                onChange={(e) => setEditDueDate(e.target.value)}
                className="w-full px-2 py-1.5 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            </div>
          </div>

          {/* 時間 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">予想時間（分）</label>
              <input
                type="number"
                value={editEstimated}
                onChange={(e) => setEditEstimated(e.target.value)}
                min="1"
                className="w-full px-2 py-1.5 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">実績時間（分）</label>
              <input
                type="number"
                value={editActual}
                onChange={(e) => setEditActual(e.target.value)}
                min="1"
                className="w-full px-2 py-1.5 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            </div>
          </div>

          {/* 保存ボタン */}
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            {saving ? '保存中...' : '変更を保存'}
          </button>

          {/* リマインダー */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Bell className="w-4 h-4 text-gray-500" />
              <span className="text-sm font-medium text-gray-700">リマインダー</span>
            </div>
            {(task.reminders ?? []).length > 0 ? (
              <ul className="space-y-1 mb-3">
                {task.reminders!.map((r) => (
                  <li key={r.id} className="text-xs text-gray-600 bg-gray-50 rounded-md px-3 py-2">
                    <span className="font-medium">{r.remind_at.slice(0, 16).replace('T', ' ')}</span>
                    {r.message && <span className="ml-2 text-gray-400">— {r.message}</span>}
                    {r.is_sent ? <span className="ml-2 text-green-500">✓送信済み</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400 mb-2">リマインダーなし</p>
            )}
            <div className="space-y-2">
              <input
                type="datetime-local"
                value={newReminderAt}
                onChange={(e) => setNewReminderAt(e.target.value)}
                className="w-full px-2 py-1.5 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
              <input
                type="text"
                value={newReminderMsg}
                onChange={(e) => setNewReminderMsg(e.target.value)}
                placeholder="メッセージ（任意）"
                className="w-full px-2 py-1.5 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
              <button
                onClick={handleAddReminder}
                disabled={!newReminderAt || addingReminder}
                className="w-full py-1.5 rounded-md bg-gray-800 text-white text-xs font-medium hover:bg-gray-700 disabled:opacity-50 transition-colors"
              >
                {addingReminder ? '設定中...' : 'リマインダーを追加'}
              </button>
            </div>
          </div>

          {/* コメント */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <MessageSquare className="w-4 h-4 text-gray-500" />
              <span className="text-sm font-medium text-gray-700">コメント</span>
            </div>
            {(task.comments ?? []).length > 0 ? (
              <ul className="space-y-2 mb-3">
                {task.comments!.map((c) => (
                  <li key={c.id} className="bg-gray-50 rounded-md px-3 py-2">
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">{c.content}</p>
                    <p className="text-xs text-gray-400 mt-1">{c.created_at.slice(0, 16).replace('T', ' ')}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400 mb-2">コメントなし</p>
            )}
            <div className="flex gap-2">
              <textarea
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="コメントを追加..."
                rows={2}
                className="flex-1 px-2 py-1.5 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400 resize-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleAddComment();
                }}
              />
              <button
                onClick={handleAddComment}
                disabled={!newComment.trim() || addingComment}
                className="px-3 py-1.5 rounded-md bg-gray-900 text-white hover:bg-gray-700 disabled:opacity-50 transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ===== メインページ =====

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [filterCategory, setFilterCategory] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [activeId, setActiveId] = useState<number | null>(null);

  // チャット
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  // DnD
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  // データ取得
  const fetchTasks = useCallback(async () => {
    const filters: Record<string, string> = {};
    if (filterCategory) filters.category_id = filterCategory;
    if (filterPriority) filters.priority = filterPriority;
    const data = await api.getTasks(filters);
    setTasks(data ?? []);
  }, [filterCategory, filterPriority]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      try {
        const [t, c] = await Promise.all([
          api.getTasks(),
          api.getCategories(),
        ]);
        setTasks(t ?? []);
        setCategories(c ?? []);
      } catch (err) {
        console.error('Tasks init error:', err);
        setError(err instanceof Error ? err.message : 'データ取得に失敗しました');
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // リマインダーポーリング（30秒）
  useEffect(() => {
    const checkReminders = async () => {
      try {
        const reminders: Array<{ task_title: string; message?: string; remind_at: string }> =
          await api.getPendingReminders();
        for (const r of reminders ?? []) {
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification(`リマインダー: ${r.task_title}`, {
              body: r.message ?? r.remind_at,
            });
          } else {
            console.info('Reminder:', r.task_title, r.message);
          }
        }
      } catch {
        // サイレント
      }
    };

    // 通知許可をリクエスト
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    const interval = setInterval(checkReminders, 30_000);
    return () => clearInterval(interval);
  }, []);

  // ===== DnD ハンドラ =====

  const activeTask = tasks.find((t) => t.id === activeId) ?? null;

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as number);
  };

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event;
    if (!over) return;

    const activeTask = tasks.find((t) => t.id === active.id);
    if (!activeTask) return;

    const overId = over.id as string | number;
    let targetStatus = activeTask.status;

    if (typeof overId === 'string' && ['todo', 'in_progress', 'done'].includes(overId)) {
      targetStatus = overId as Task['status'];
    } else {
      const overTask = tasks.find((t) => t.id === overId);
      if (overTask) targetStatus = overTask.status;
    }

    if (targetStatus !== activeTask.status) {
      setTasks((prev) =>
        prev.map((t) => (t.id === activeTask.id ? { ...t, status: targetStatus as Task['status'] } : t))
      );
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    if (!over) return;

    const draggedTask = tasks.find((t) => t.id === active.id);
    if (!draggedTask) return;

    // APIで永続化
    api.updateTask(draggedTask.id, { status: draggedTask.status }).catch(console.error);
  };

  // ===== フィルタ済みタスク =====

  const filteredTasks = tasks.filter((t) => {
    if (filterCategory && t.category_id?.toString() !== filterCategory) return false;
    if (filterPriority && t.priority !== filterPriority) return false;
    return true;
  });

  const columnTasks = (status: string) => filteredTasks.filter((t) => t.status === status);

  // ===== サマリー計算 =====

  const totalEstimated = tasks.reduce((sum, t) => sum + (t.estimated_minutes ?? 0), 0);
  const doneTasks = tasks.filter((t) => t.status === 'done').length;
  const todayStr = new Date().toISOString().slice(0, 10);
  const todayTasks = tasks.filter((t) => t.due_date?.slice(0, 10) === todayStr);
  const todayEstimated = todayTasks.reduce((sum, t) => sum + (t.estimated_minutes ?? 0), 0);

  // ===== チャット送信 =====

  const handleChatSubmit = async () => {
    if (!chatInput.trim() || chatLoading) return;
    const msg = chatInput.trim();
    setChatInput('');
    setChatMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setChatLoading(true);
    try {
      const result = await api.chat(msg);
      setChatMessages((prev) => [...prev, { role: 'ai', content: result.message ?? '完了しました' }]);
      // タスクリストを更新
      fetchTasks();
    } catch (err) {
      setChatMessages((prev) => [...prev, { role: 'ai', content: `エラー: ${err}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  // ===== レンダリング =====

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ヘッダー */}
      <header className="bg-white border-b border-gray-200 px-4 md:px-6 py-4 flex-shrink-0">
        <div className="max-w-7xl mx-auto flex flex-col gap-3 md:flex-row md:items-center md:gap-4">
          <div className="flex items-center gap-2">
            <h1 className="text-base font-semibold text-gray-900">タスク管理</h1>
          </div>

          {/* フィルター */}
          <div className="flex gap-2 md:ml-auto items-center">
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="px-2 py-1.5 rounded-md border border-gray-200 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
            >
              <option value="">全カテゴリ</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              value={filterPriority}
              onChange={(e) => setFilterPriority(e.target.value)}
              className="px-2 py-1.5 rounded-md border border-gray-200 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
            >
              <option value="">全優先度</option>
              <option value="high">H</option>
              <option value="medium">M</option>
              <option value="low">L</option>
            </select>
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-700 transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">追加</span>
            </button>

            {/* サマリー */}
            <span className="text-xs text-gray-400 ml-2 hidden md:inline">
              今日 {todayTasks.length}件　完了 {doneTasks}/{tasks.length}
              {totalEstimated > 0 && `　計 ${Math.floor(totalEstimated / 60)}h${totalEstimated % 60}m`}
            </span>
          </div>
        </div>
      </header>

      {/* メインコンテンツ */}
      <div className="flex-1 flex overflow-hidden">
        {/* カンバンボード */}
        <div className="flex-1 overflow-auto p-4 md:p-6">
          {loading ? (
            <div className="flex justify-center items-center h-64">
              <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
          ) : error ? (
            <div className="flex flex-col justify-center items-center h-64 gap-3">
              <p className="text-red-500 text-sm">{error}</p>
              <button onClick={() => { setError(null); setLoading(true); }} className="text-xs text-gray-500 underline">再試行</button>
            </div>
          ) : (
            <DndContext
              sensors={sensors}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDragEnd={handleDragEnd}
            >
              <div className="flex flex-col md:flex-row gap-4 max-w-7xl mx-auto">
                {(['todo', 'in_progress', 'done'] as const).map((status) => (
                  <KanbanColumn
                    key={status}
                    status={status}
                    tasks={columnTasks(status)}
                    onTaskClick={(task) => setSelectedTaskId(task.id)}
                  />
                ))}
              </div>

              <DragOverlay>
                {activeTask && (
                  <TaskCard task={activeTask} overlay />
                )}
              </DragOverlay>
            </DndContext>
          )}
        </div>

        {/* サイドパネル */}
        {selectedTaskId != null && (
          <TaskDetailPanel
            taskId={selectedTaskId}
            categories={categories}
            onClose={() => setSelectedTaskId(null)}
            onUpdate={(updated) => {
              setTasks((prev) => prev.map((t) => (t.id === updated.id ? { ...t, ...updated } : t)));
            }}
            onDelete={(id) => {
              setTasks((prev) => prev.filter((t) => t.id !== id));
              setSelectedTaskId(null);
            }}
          />
        )}
      </div>

      {/* AI チャットバー */}
      <div className="bg-white border-t border-gray-200 px-4 md:px-6 py-3 flex-shrink-0">
        <div className="max-w-7xl mx-auto">
          {chatMessages.length > 0 && (
            <div className="mb-2 max-h-32 overflow-y-auto space-y-0.5">
              {chatMessages.slice(-4).map((m, i) => (
                <div
                  key={i}
                  className={`text-xs py-1 pl-3 ${
                    m.role === 'user'
                      ? 'border-l-2 border-gray-400 text-gray-900'
                      : 'border-l-2 border-gray-200 text-gray-500'
                  }`}
                >
                  {m.content}
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2 items-center">
            <Bot className="w-4 h-4 text-gray-400 flex-shrink-0" />
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleChatSubmit();
                }
              }}
              placeholder="「明日の会議をリマインドして」「設計レビューのタスクを追加して（高優先度）」"
              className="flex-1 px-3 py-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400 bg-white"
              disabled={chatLoading}
            />
            <button
              onClick={handleChatSubmit}
              disabled={!chatInput.trim() || chatLoading}
              className="px-3 py-2 bg-gray-900 text-white rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
            >
              {chatLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* タスク作成モーダル */}
      {showCreateModal && (
        <CreateTaskModal
          categories={categories}
          onClose={() => setShowCreateModal(false)}
          onCreate={(task) => {
            setTasks((prev) => [task, ...prev]);
            setShowCreateModal(false);
          }}
        />
      )}
    </div>
  );
}
