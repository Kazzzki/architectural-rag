'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { X, Trash2, Bell, MessageSquare, Send, Loader2, Plus, CheckSquare } from 'lucide-react';
import type { Task, Category, Label, Milestone, Comment, Reminder } from './types';
import { api } from './taskApi';

export default function TaskDetailPanel({
  taskId,
  categories,
  projects,
  labels: allLabels,
  milestones,
  onClose,
  onUpdate,
  onDelete,
}: {
  taskId: number;
  categories: Category[];
  projects: string[];
  labels: Label[];
  milestones: Milestone[];
  onClose: () => void;
  onUpdate: (task: Task) => void;
  onDelete: (id: number) => void;
}) {
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [subtasks, setSubtasks] = useState<Task[]>([]);

  const [editTitle, setEditTitle] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editStatus, setEditStatus] = useState<Task['status']>('todo');
  const [editPriority, setEditPriority] = useState<Task['priority']>('medium');
  const [editCategory, setEditCategory] = useState('');
  const [editDueDate, setEditDueDate] = useState('');
  const [editEstimated, setEditEstimated] = useState('');
  const [editActual, setEditActual] = useState('');
  const [editProject, setEditProject] = useState('');
  const [editAssignee, setEditAssignee] = useState('');
  const [editMilestone, setEditMilestone] = useState('');

  const [newComment, setNewComment] = useState('');
  const [addingComment, setAddingComment] = useState(false);
  const [newReminderAt, setNewReminderAt] = useState('');
  const [newReminderMsg, setNewReminderMsg] = useState('');
  const [addingReminder, setAddingReminder] = useState(false);
  const [newSubtaskTitle, setNewSubtaskTitle] = useState('');
  const [addingSubtask, setAddingSubtask] = useState(false);

  const loadTask = useCallback(async () => {
    setLoading(true);
    try {
      const [t, subs] = await Promise.all([
        api.getTask(taskId),
        api.getSubtasks(taskId).catch(() => []),
      ]);
      setTask(t);
      setSubtasks(subs ?? []);
      setEditTitle(t.title);
      setEditDesc(t.description ?? '');
      setEditStatus(t.status);
      setEditPriority(t.priority);
      setEditCategory(t.category_id?.toString() ?? '');
      setEditDueDate(t.due_date ?? '');
      setEditEstimated(t.estimated_minutes?.toString() ?? '');
      setEditActual(t.actual_minutes?.toString() ?? '');
      setEditProject(t.project_name ?? '');
      setEditAssignee(t.assignee_name ?? '');
      setEditMilestone(t.milestone_id?.toString() ?? '');
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => { loadTask(); }, [loadTask]);

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
        project_name: editProject || undefined,
        assignee_name: editAssignee || undefined,
        milestone_id: editMilestone ? parseInt(editMilestone) : undefined,
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

  const handleAddSubtask = async () => {
    if (!task || !newSubtaskTitle.trim()) return;
    setAddingSubtask(true);
    try {
      const sub = await api.createTask({
        title: newSubtaskTitle.trim(),
        parent_id: task.id,
        status: 'todo',
        priority: 'medium',
        project_name: task.project_name,
      });
      setSubtasks((prev) => [...prev, sub]);
      setNewSubtaskTitle('');
    } finally {
      setAddingSubtask(false);
    }
  };

  const handleToggleSubtask = async (sub: Task) => {
    const newStatus = sub.status === 'done' ? 'todo' : 'done';
    setSubtasks((prev) => prev.map((s) => s.id === sub.id ? { ...s, status: newStatus as Task['status'] } : s));
    await api.updateTask(sub.id, { status: newStatus });
  };

  const handleDelete = async () => {
    if (!task) return;
    if (!confirm(`「${task.title}」を削除しますか？`)) return;
    await api.deleteTask(task.id);
    onDelete(task.id);
  };

  const handleAttachLabel = async (labelId: number) => {
    if (!task) return;
    const currentIds = task.label_ids?.split(',').filter(Boolean).map(Number) ?? [];
    if (currentIds.includes(labelId)) {
      await api.detachLabel(task.id, labelId);
    } else {
      await api.attachLabels(task.id, [...currentIds, labelId]);
    }
    loadTask();
  };

  const taskLabelIds = task?.label_ids?.split(',').filter(Boolean).map(Number) ?? [];

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40 md:hidden" onClick={onClose} />
      <div className="fixed inset-x-0 bottom-0 z-50 max-h-[85vh] rounded-t-2xl shadow-2xl md:static md:inset-auto md:z-auto md:max-h-none md:rounded-none md:shadow-none w-full md:w-96 flex-shrink-0 h-auto md:h-full border-l-0 md:border-l border-gray-200 bg-white flex flex-col">
        <div className="flex justify-center py-2 md:hidden">
          <div className="w-10 h-1 bg-gray-300 rounded-full" />
        </div>
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">タスク詳細</h3>
          <div className="flex gap-2">
            <button onClick={handleDelete} className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-700" title="削除">
              <Trash2 className="w-4 h-4" />
            </button>
            <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : !task ? (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">読み込みエラー</div>
        ) : (
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">タイトル</label>
              <input type="text" value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">プロジェクト</label>
                <select value={editProject} onChange={(e) => setEditProject(e.target.value)}
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                  <option value="">なし</option>
                  {projects.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">担当者</label>
                <input type="text" value={editAssignee} onChange={(e) => setEditAssignee(e.target.value)}
                  placeholder="担当者名" className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">説明</label>
              <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)} rows={3}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm resize-none" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">ステータス</label>
                <select value={editStatus} onChange={(e) => setEditStatus(e.target.value as Task['status'])}
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                  <option value="todo">ToDo</option>
                  <option value="in_progress">進行中</option>
                  <option value="done">完了</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">優先度</label>
                <select value={editPriority} onChange={(e) => setEditPriority(e.target.value as Task['priority'])}
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                  <option value="high">高</option>
                  <option value="medium">中</option>
                  <option value="low">低</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">カテゴリ</label>
                <select value={editCategory} onChange={(e) => setEditCategory(e.target.value)}
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                  <option value="">なし</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">期限</label>
                <input type="date" value={editDueDate} onChange={(e) => setEditDueDate(e.target.value)}
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm" />
              </div>
            </div>

            {milestones.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">マイルストーン</label>
                <select value={editMilestone} onChange={(e) => setEditMilestone(e.target.value)}
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                  <option value="">なし</option>
                  {milestones.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">予想時間（分）</label>
                <input type="number" value={editEstimated} onChange={(e) => setEditEstimated(e.target.value)} min="1"
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">実績時間（分）</label>
                <input type="number" value={editActual} onChange={(e) => setEditActual(e.target.value)} min="1"
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm" />
              </div>
            </div>

            {/* Labels */}
            {allLabels.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">ラベル</label>
                <div className="flex flex-wrap gap-1.5">
                  {allLabels.map((l) => (
                    <button key={l.id} onClick={() => handleAttachLabel(l.id)}
                      className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                        taskLabelIds.includes(l.id)
                          ? 'text-white border-transparent'
                          : 'text-gray-500 border-gray-200 hover:border-gray-400'
                      }`}
                      style={taskLabelIds.includes(l.id) ? { backgroundColor: l.color } : {}}>
                      {l.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <button onClick={handleSave} disabled={saving}
              className="w-full py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-700 disabled:opacity-50 transition-colors">
              {saving ? '保存中...' : '変更を保存'}
            </button>

            {/* Subtasks */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <CheckSquare className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-medium text-gray-700">サブタスク</span>
                {subtasks.length > 0 && (
                  <span className="text-xs text-gray-400">
                    {subtasks.filter((s) => s.status === 'done').length}/{subtasks.length}
                  </span>
                )}
              </div>
              {subtasks.length > 0 && (
                <ul className="space-y-1 mb-2">
                  {subtasks.map((sub) => (
                    <li key={sub.id} className="flex items-center gap-2 py-1">
                      <button onClick={() => handleToggleSubtask(sub)}
                        className={`w-4 h-4 rounded border-2 shrink-0 flex items-center justify-center transition-colors ${
                          sub.status === 'done' ? 'bg-gray-900 border-gray-900 text-white' : 'border-gray-300 hover:border-gray-500'
                        }`}>
                        {sub.status === 'done' && <CheckSquare className="w-3 h-3" />}
                      </button>
                      <span className={`text-sm ${sub.status === 'done' ? 'line-through text-gray-400' : 'text-gray-700'}`}>
                        {sub.title}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex gap-2">
                <input type="text" value={newSubtaskTitle} onChange={(e) => setNewSubtaskTitle(e.target.value)}
                  placeholder="サブタスクを追加..."
                  className="flex-1 px-2 py-1.5 rounded-lg border border-gray-200 text-sm"
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); handleAddSubtask(); } }} />
                <button onClick={handleAddSubtask} disabled={!newSubtaskTitle.trim() || addingSubtask}
                  className="px-2 py-1.5 rounded-md bg-gray-900 text-white hover:bg-gray-700 disabled:opacity-50">
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Reminders */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Bell className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-medium text-gray-700">リマインダー</span>
              </div>
              {(task.reminders ?? []).length > 0 ? (
                <ul className="space-y-1 mb-3">
                  {task.reminders!.map((r) => {
                    const isAuto = r.message?.endsWith('の期限日です') ?? false;
                    return (
                      <li key={r.id} className="text-xs text-gray-600 bg-gray-50 rounded-md px-3 py-2">
                        {isAuto && <span className="mr-1.5 text-gray-400 border border-gray-200 rounded px-1 py-0.5 text-[10px]">自動</span>}
                        <span className="font-medium">{r.remind_at.slice(0, 16).replace('T', ' ')}</span>
                        {r.message && <span className="ml-2 text-gray-400">— {r.message}</span>}
                        {r.is_sent ? <span className="ml-2 text-gray-400">✓送信済み</span> : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-xs text-gray-400 mb-2">リマインダーなし</p>
              )}
              <div className="space-y-2">
                <input type="datetime-local" value={newReminderAt} onChange={(e) => setNewReminderAt(e.target.value)}
                  className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm" />
                <input type="text" value={newReminderMsg} onChange={(e) => setNewReminderMsg(e.target.value)}
                  placeholder="メッセージ（任意）" className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm" />
                <button onClick={handleAddReminder} disabled={!newReminderAt || addingReminder}
                  className="w-full py-1.5 rounded-md bg-gray-900 text-white text-xs font-medium hover:bg-gray-700 disabled:opacity-50">
                  {addingReminder ? '設定中...' : 'リマインダーを追加'}
                </button>
              </div>
            </div>

            {/* Comments */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <MessageSquare className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-medium text-gray-700">コメント</span>
              </div>
              {(task.comments ?? []).length > 0 ? (
                <ul className="space-y-2 mb-3">
                  {task.comments!.map((c) => (
                    <li key={c.id} className="bg-gray-50 rounded-lg px-3 py-2">
                      <p className="text-sm text-gray-700 whitespace-pre-wrap">{c.content}</p>
                      <p className="text-xs text-gray-400 mt-1">{c.created_at.slice(0, 16).replace('T', ' ')}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-gray-400 mb-2">コメントなし</p>
              )}
              <div className="flex gap-2">
                <textarea value={newComment} onChange={(e) => setNewComment(e.target.value)}
                  placeholder="コメントを追加..." rows={2}
                  className="flex-1 px-2 py-1.5 rounded-lg border border-gray-200 text-sm resize-none"
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleAddComment(); }} />
                <button onClick={handleAddComment} disabled={!newComment.trim() || addingComment}
                  className="px-3 py-1.5 rounded-md bg-gray-900 text-white hover:bg-gray-700 disabled:opacity-50">
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
