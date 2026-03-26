'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue } from '@/lib/issue_types';
import { X, Trash2, Sparkles } from 'lucide-react';

interface BatchActionBarProps {
  selectedIds: string[];
  issues: Issue[];
  onClearSelection: () => void;
  onRefresh: () => void;
  onAIInfer: (issueIds: string[]) => void;
}

const STATUS_OPTIONS = ['発生中', '対応中', '解決済み'] as const;
const PRIORITY_OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'normal', label: 'Normal' },
  { value: 'minor', label: 'Minor' },
] as const;

export default function BatchActionBar({
  selectedIds, issues, onClearSelection, onRefresh, onAIInfer,
}: BatchActionBarProps) {
  const [loading, setLoading] = useState(false);

  if (selectedIds.length < 2) return null;

  async function batchUpdate(updates: Record<string, string>) {
    setLoading(true);
    try {
      const res = await authFetch('/api/issues/batch', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_ids: selectedIds, updates }),
      });
      if (res.ok) {
        onRefresh();
        onClearSelection();
      }
    } finally {
      setLoading(false);
    }
  }

  async function batchDelete() {
    if (!window.confirm(`${selectedIds.length}件の課題を削除しますか？この操作は取り消せません。`)) return;
    setLoading(true);
    try {
      await Promise.all(selectedIds.map((id) => authFetch(`/api/issues/${id}`, { method: 'DELETE' })));
      onRefresh();
      onClearSelection();
    } finally {
      setLoading(false);
    }
  }

  const canAIInfer = selectedIds.length >= 2 && selectedIds.length <= 8;

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 bg-white/95 backdrop-blur border border-gray-200 rounded-2xl shadow-xl px-4 py-2.5">
      <span className="text-sm font-medium text-gray-700 mr-1">
        {selectedIds.length}件選択
      </span>

      <div className="w-px h-6 bg-gray-200" />

      {/* ステータス一括変更 */}
      <select
        onChange={(e) => { if (e.target.value) batchUpdate({ status: e.target.value }); e.target.value = ''; }}
        disabled={loading}
        className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white"
        defaultValue=""
      >
        <option value="" disabled>ステータス</option>
        {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>

      {/* 優先度一括変更 */}
      <select
        onChange={(e) => { if (e.target.value) batchUpdate({ priority: e.target.value }); e.target.value = ''; }}
        disabled={loading}
        className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white"
        defaultValue=""
      >
        <option value="" disabled>優先度</option>
        {PRIORITY_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
      </select>

      {/* AI因果推定 */}
      {canAIInfer && (
        <>
          <div className="w-px h-6 bg-gray-200" />
          <button
            onClick={() => onAIInfer(selectedIds)}
            disabled={loading}
            className="flex items-center gap-1 text-xs text-violet-600 border border-violet-300 rounded-lg px-2.5 py-1.5 hover:bg-violet-50 disabled:opacity-40"
          >
            <Sparkles size={13} />
            AI因果推定
          </button>
        </>
      )}

      <div className="w-px h-6 bg-gray-200" />

      {/* 一括削除 */}
      <button
        onClick={batchDelete}
        disabled={loading}
        className="flex items-center gap-1 text-xs text-red-600 border border-red-200 rounded-lg px-2.5 py-1.5 hover:bg-red-50 disabled:opacity-40"
      >
        <Trash2 size={13} />
        削除
      </button>

      {/* 選択解除 */}
      <button
        onClick={onClearSelection}
        className="text-gray-400 hover:text-gray-600 p-1"
        title="選択解除"
      >
        <X size={16} />
      </button>
    </div>
  );
}
