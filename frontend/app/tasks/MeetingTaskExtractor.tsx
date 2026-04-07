'use client';

import React, { useState, useEffect } from 'react';
import { X, Loader2, CheckSquare } from 'lucide-react';
import type { Task, Meeting } from './types';
import { api } from './taskApi';

export default function MeetingTaskExtractor({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingMeetings, setLoadingMeetings] = useState(true);
  const [extractedTasks, setExtractedTasks] = useState<Partial<Task>[]>([]);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const data = await api.getMeetings();
        setMeetings(data ?? []);
      } catch (e) {
        console.warn('meetings load:', e);
        setMeetings([]);
      } finally {
        setLoadingMeetings(false);
      }
    })();
  }, []);

  const handleExtract = async () => {
    if (!selectedMeeting) return;
    setLoading(true);
    setError('');
    setExtractedTasks([]);
    try {
      const result = await api.extractFromMeeting(parseInt(selectedMeeting));
      const tasks = result.tasks ?? result.proposed_tasks ?? [];
      setExtractedTasks(tasks);
      setChecked(new Set(tasks.map((_: unknown, i: number) => i)));
    } catch (err) {
      setError(err instanceof Error ? err.message : '抽出に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  const toggleCheck = (idx: number) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  const handleCreate = async () => {
    const selected = extractedTasks.filter((_, i) => checked.has(i));
    if (selected.length === 0) return;
    setCreating(true);
    const meetingId = parseInt(selectedMeeting);
    try {
      await api.bulkCreate(selected.map((t) => ({ ...t, source_meeting_id: meetingId, source_type: 'meeting' } as Partial<Task>)));
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : '作成に失敗しました');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white shadow-lg w-full sm:max-w-2xl h-full sm:h-auto sm:max-h-[90vh] sm:rounded-md flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">議事録からタスク抽出</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-500">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-500 mb-1">会議を選択</label>
              {loadingMeetings ? (
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <Loader2 className="w-4 h-4 animate-spin" />読み込み中...
                </div>
              ) : (
                <select value={selectedMeeting} onChange={(e) => setSelectedMeeting(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm bg-white">
                  <option value="">選択してください</option>
                  {meetings.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.title} ({m.created_at?.slice(0, 10)})
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex items-end">
              <button onClick={handleExtract} disabled={!selectedMeeting || loading}
                className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-700 disabled:opacity-50 flex items-center gap-2">
                {loading ? <><Loader2 className="w-4 h-4 animate-spin" />抽出中...</> : 'タスクを抽出'}
              </button>
            </div>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        {extractedTasks.length > 0 && (
          <div className="flex-1 overflow-y-auto border-t border-gray-100 p-6">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-700">{extractedTasks.length}件のタスクを検出</span>
              <span className="text-xs text-gray-400">{checked.size}件選択中</span>
            </div>

            <div className="space-y-2 mb-4">
              {extractedTasks.map((task, i) => (
                <div key={`${task.title}-${i}`}
                  className={`flex items-start gap-3 p-3 rounded-md border transition-colors ${
                    checked.has(i) ? 'border-gray-300 bg-gray-50' : 'border-gray-100'
                  }`}>
                  <input type="checkbox" checked={checked.has(i)} onChange={() => toggleCheck(i)}
                    className="mt-1 rounded border-gray-300" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900">{task.title}</p>
                    <div className="flex gap-2 text-xs text-gray-400 mt-1">
                      {task.assignee_name && <span>担当: {task.assignee_name}</span>}
                      {task.due_date && <span>期限: {task.due_date}</span>}
                      {task.priority && <span>優先度: {task.priority}</span>}
                    </div>
                    {task.description && (
                      <p className="text-xs text-gray-500 mt-1">{task.description}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <button onClick={handleCreate} disabled={checked.size === 0 || creating}
              className="w-full py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-700 disabled:opacity-50 flex items-center justify-center gap-2">
              {creating ? (
                <><Loader2 className="w-4 h-4 animate-spin" />作成中...</>
              ) : (
                <><CheckSquare className="w-4 h-4" />選択したタスクを作成 ({checked.size}件)</>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
