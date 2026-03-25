'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue } from '@/lib/issue_types';
import { X } from 'lucide-react';
import NoteTimeline from './NoteTimeline';
import AIInvestigatePanel from './AIInvestigatePanel';

interface IssueDetailDrawerProps {
  issue: Issue | null;
  onClose: () => void;
  onUpdated: (updated: Issue) => void;
}

const PRIORITY_OPTIONS = ['critical', 'normal', 'minor'] as const;
const STATUS_OPTIONS = ['発生中', '対応中', '解決済み'] as const;

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  normal:   'bg-blue-100 text-blue-700 border-blue-200',
  minor:    'bg-gray-100 text-gray-500 border-gray-200',
};

const STATUS_BADGE: Record<string, string> = {
  '発生中': 'bg-red-100 text-red-600',
  '対応中': 'bg-orange-100 text-orange-600',
  '解決済み': 'bg-green-100 text-green-600',
};

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
    <>
      {/* オーバーレイ (モバイルのみ) */}
      <div
        className="fixed inset-0 bg-black/30 z-40 md:hidden"
        onClick={onClose}
      />

      {/* ドロワー本体
          モバイル: 下からスライドするボトムシート
          デスクトップ: 右からスライドするサイドパネル */}
      <div
        className={[
          'fixed z-50 flex flex-col bg-white shadow-2xl',
          // モバイル: ボトムシート
          'bottom-0 left-0 right-0 max-h-[78vh] rounded-t-2xl border-t border-gray-200',
          // デスクトップ: サイドパネル
          'md:bottom-auto md:left-auto md:right-0 md:top-0 md:max-h-none md:h-full md:w-80 md:rounded-none md:border-t-0 md:border-l md:border-gray-200',
        ].join(' ')}
        style={{ transition: 'transform 0.25s ease-out' }}
      >
        {/* ドラッグハンドル (モバイルのみ) */}
        <div className="md:hidden flex justify-center pt-3 pb-1 flex-shrink-0">
          <div className="w-10 h-1 bg-gray-300 rounded-full" />
        </div>

        {/* ヘッダー */}
        <div className="flex items-start justify-between px-4 py-3 border-b border-gray-100 flex-shrink-0">
          <div className="flex-1 min-w-0 pr-2">
            <div className="font-semibold text-sm text-gray-800 leading-tight">{issue.title}</div>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${PRIORITY_BADGE[priority] ?? PRIORITY_BADGE.normal}`}>
                {priority === 'critical' ? 'Critical' : priority === 'normal' ? 'Normal' : 'Minor'}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[status] ?? ''}`}>
                {status}
              </span>
              <span className="text-xs text-gray-400">{issue.category}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 flex-shrink-0 p-1 -mr-1 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* 重要度 */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">重要度</label>
            <select
              value={priority}
              onChange={(e) => {
                setPriority(e.target.value);
                patch({ priority: e.target.value });
              }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {PRIORITY_OPTIONS.map((p) => (
                <option key={p} value={p}>{p === 'critical' ? 'Critical' : p === 'normal' ? 'Normal' : 'Minor'}</option>
              ))}
            </select>
          </div>

          {/* ステータス */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">ステータス</label>
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                patch({ status: e.target.value });
              }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          {/* 詳細説明 */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">詳細説明</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => patch({ description })}
              rows={3}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            />
          </div>

          {/* 次のアクション */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">次のアクション</label>
            <textarea
              value={actionNext}
              onChange={(e) => setActionNext(e.target.value)}
              onBlur={() => patch({ action_next: actionNext })}
              rows={3}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            />
          </div>

          {/* 推定原因 */}
          {issue.cause && (
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">推定原因</label>
              <div className="text-sm text-gray-700 bg-gray-50 rounded-lg p-3 leading-relaxed">{issue.cause}</div>
            </div>
          )}

          {/* 影響 */}
          {issue.impact && (
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">影響</label>
              <div className="text-sm text-gray-700 bg-gray-50 rounded-lg p-3 leading-relaxed">{issue.impact}</div>
            </div>
          )}

          {/* タイムラインメモ */}
          <NoteTimeline issueId={issue.id} />

          {/* AI調査 */}
          <AIInvestigatePanel issue={issue} />
        </div>

        {/* フッター: 折りたたみトグル */}
        <div className="p-4 border-t border-gray-100 flex-shrink-0 pb-safe">
          <button
            onClick={toggleCollapse}
            disabled={saving}
            className="w-full text-sm border border-gray-200 rounded-xl py-2.5 hover:bg-gray-50 text-gray-600 font-medium transition-colors disabled:opacity-50"
          >
            {issue.is_collapsed === 1 ? '子ノードを展開する' : '子ノードを折りたたむ'}
          </button>
        </div>
      </div>
    </>
  );
}
