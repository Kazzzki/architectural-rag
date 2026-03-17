'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue } from '@/lib/issue_types';
import { X } from 'lucide-react';

interface IssueDetailDrawerProps {
  issue: Issue | null;
  onClose: () => void;
  onUpdated: (updated: Issue) => void;
}

const PRIORITY_OPTIONS = ['critical', 'normal', 'minor'] as const;
const STATUS_OPTIONS = ['発生中', '対応中', '解決済み'] as const;

export default function IssueDetailDrawer({ issue, onClose, onUpdated }: IssueDetailDrawerProps) {
  const [priority, setPriority] = useState<string>('normal');
  const [status, setStatus] = useState<string>('発生中');
  const [actionNext, setActionNext] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (issue) {
      setPriority(issue.priority);
      setStatus(issue.status);
      setActionNext(issue.action_next ?? '');
      setDescription(issue.description ?? '');
    }
  }, [issue]);

  async function patch(body: object) {
    if (!issue) return;
    setSaving(true);
    try {
      const res = await authFetch(`/api/issues/${issue.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const updated: Issue = await res.json();
        onUpdated(updated);
      }
    } finally {
      setSaving(false);
    }
  }

  async function toggleCollapse() {
    if (!issue) return;
    await patch({ is_collapsed: issue.is_collapsed === 1 ? 0 : 1 });
  }

  if (!issue) return null;

  return (
    <div
      className="fixed z-50 bg-white shadow-2xl flex flex-col inset-x-0 bottom-0 h-[60vh] rounded-t-2xl border-t border-gray-200 md:left-auto md:right-0 md:top-0 md:bottom-auto md:h-full md:w-80 md:rounded-none md:border-l md:border-t-0"
      style={{ transition: 'transform 0.2s' }}
    >
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <div className="font-semibold text-sm text-gray-800 truncate">{issue.title}</div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-700 flex-shrink-0">
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* 重要度 */}
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1">重要度</label>
          <select
            value={priority}
            onChange={(e) => {
              setPriority(e.target.value);
              patch({ priority: e.target.value });
            }}
            className="w-full text-sm border border-gray-300 rounded px-2 py-1"
          >
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p} value={p}>{p === 'critical' ? 'Critical' : p === 'normal' ? 'Normal' : 'Minor'}</option>
            ))}
          </select>
        </div>

        {/* ステータス */}
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1">ステータス</label>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              patch({ status: e.target.value });
            }}
            className="w-full text-sm border border-gray-300 rounded px-2 py-1"
          >
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {/* 詳細説明 */}
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1">詳細説明</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={() => patch({ description })}
            rows={3}
            className="w-full text-sm border border-gray-300 rounded px-2 py-1 resize-none"
          />
        </div>

        {/* 次のアクション */}
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1">次のアクション</label>
          <textarea
            value={actionNext}
            onChange={(e) => setActionNext(e.target.value)}
            onBlur={() => patch({ action_next: actionNext })}
            rows={3}
            className="w-full text-sm border border-gray-300 rounded px-2 py-1 resize-none"
          />
        </div>

        {/* 原因 */}
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1">推定原因</label>
          <div className="text-sm text-gray-700 bg-gray-50 rounded p-2">{issue.cause || '—'}</div>
        </div>

        {/* 影響 */}
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1">影響</label>
          <div className="text-sm text-gray-700 bg-gray-50 rounded p-2">{issue.impact || '—'}</div>
        </div>

        {/* カテゴリ */}
        <div className="flex gap-4 text-xs text-gray-500">
          <span>カテゴリ: {issue.category}</span>
          <span>プロジェクト: {issue.project_name}</span>
        </div>
      </div>

      {/* フッター: 折りたたみトグル */}
      <div className="p-4 border-t border-gray-200">
        <button
          onClick={toggleCollapse}
          disabled={saving}
          className="w-full text-sm border border-gray-300 rounded py-2 hover:bg-gray-50 text-gray-700 transition-colors"
        >
          {issue.is_collapsed === 1 ? '子ノードを展開する' : '子ノードを折りたたむ'}
        </button>
      </div>
    </div>
  );
}
