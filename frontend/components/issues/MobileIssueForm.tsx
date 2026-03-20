'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, Loader2 } from 'lucide-react';
import { authFetch } from '@/lib/api';
import { CaptureResponse } from '@/lib/issue_types';

interface Props {
  projectName: string;
  members?: string[];
  onIssueAdded: (resp: CaptureResponse) => void;
  onClose: () => void;
}

// -- Chip component --
function Chip({ label, selected, color, onClick }: {
  label: string; selected: boolean; color: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`min-h-[44px] px-4 rounded-full border text-sm font-medium transition-all active:scale-95 ${
        selected ? color : 'bg-gray-50 text-gray-500 border-gray-200'
      }`}
    >
      {label}
    </button>
  );
}

const CATEGORY_ITEMS = [
  { value: '工程', icon: '📅' },
  { value: 'コスト', icon: '💰' },
  { value: '品質', icon: '✅' },
  { value: '安全', icon: '⚠️' },
];

const PRIORITY_ITEMS = [
  { value: 'critical', label: '緊急', color: 'bg-red-600 text-white border-red-600' },
  { value: 'normal', label: '通常', color: 'bg-blue-600 text-white border-blue-600' },
  { value: 'minor', label: '軽微', color: 'bg-gray-500 text-white border-gray-500' },
];

export default function MobileIssueForm({ projectName, members = [], onIssueAdded, onClose }: Props) {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('工程');
  const [priority, setPriority] = useState('normal');
  const [assignee, setAssignee] = useState('');
  const [deadline, setDeadline] = useState('');
  const [showMore, setShowMore] = useState(false);
  const [description, setDescription] = useState('');
  const [actionNext, setActionNext] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => { titleRef.current?.focus(); }, []);

  const handleFocus = useCallback((e: React.FocusEvent) => {
    setTimeout(() => (e.target as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!title.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: title.trim(), project_name: projectName, skip_ai: true }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: CaptureResponse = await res.json();

      const patch: Record<string, string> = { category, priority };
      if (assignee.trim()) patch.assignee = assignee.trim();
      if (deadline) patch.deadline = deadline;
      if (description.trim()) patch.description = description.trim();
      if (actionNext.trim()) patch.action_next = actionNext.trim();

      await authFetch(`/api/issues/${data.issue.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      onIssueAdded(data);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : '登録に失敗しました');
    } finally {
      setSubmitting(false);
    }
  }, [title, category, priority, assignee, deadline, description, actionNext, projectName, submitting, onIssueAdded, onClose]);

  return (
    <div className="flex flex-col h-full max-h-[80vh]">
      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">

        {/* ===== 何が起きた？ ===== */}
        <div>
          <input
            ref={titleRef}
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onFocus={handleFocus}
            placeholder="何が起きた？"
            className="w-full text-lg font-bold border-0 border-b-2 border-blue-400 bg-transparent px-0 py-3 placeholder-gray-300 focus:outline-none focus:border-blue-600"
          />
        </div>

        {/* ===== カテゴリ（横スクロール） ===== */}
        <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {CATEGORY_ITEMS.map(c => (
            <button
              key={c.value}
              onClick={() => setCategory(c.value)}
              className={`flex items-center gap-1.5 min-h-[44px] px-4 rounded-full border text-sm font-medium whitespace-nowrap transition-all active:scale-95 ${
                category === c.value
                  ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                  : 'bg-white text-gray-600 border-gray-200'
              }`}
            >
              <span>{c.icon}</span> {c.value}
            </button>
          ))}
        </div>

        {/* ===== 優先度 ===== */}
        <div className="flex gap-2">
          {PRIORITY_ITEMS.map(p => (
            <Chip
              key={p.value}
              label={p.label}
              selected={priority === p.value}
              color={p.color}
              onClick={() => setPriority(p.value)}
            />
          ))}
        </div>

        {/* ===== 誰が・いつまでに ===== */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] text-gray-400 mb-1 block">誰が</label>
            <input
              type="text"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              onFocus={handleFocus}
              list="members"
              placeholder="担当者"
              className="w-full text-sm border border-gray-200 rounded-xl px-3 min-h-[44px] bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            {members.length > 0 && <datalist id="members">{members.map(m => <option key={m} value={m} />)}</datalist>}
          </div>
          <div>
            <label className="text-[11px] text-gray-400 mb-1 block">いつまでに</label>
            <input
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-xl px-3 min-h-[44px] bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>
        </div>

        {/* ===== 詳細（折りたたみ） ===== */}
        {!showMore ? (
          <button
            onClick={() => setShowMore(true)}
            className="flex items-center gap-1 text-sm text-blue-600 py-2"
          >
            <ChevronDown size={16} /> 詳細を追加
          </button>
        ) : (
          <div className="space-y-3 pt-1 border-t border-gray-100">
            <div>
              <label className="text-[11px] text-gray-400 mb-1 block">詳細</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onFocus={handleFocus}
                rows={2}
                placeholder="状況の詳細..."
                className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2.5 bg-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
            <div>
              <label className="text-[11px] text-gray-400 mb-1 block">次にやること</label>
              <textarea
                value={actionNext}
                onChange={(e) => setActionNext(e.target.value)}
                onFocus={handleFocus}
                rows={2}
                placeholder="次のアクション..."
                className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2.5 bg-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
          </div>
        )}

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2">{error}</div>
        )}
      </div>

      {/* ===== 登録ボタン ===== */}
      <div className="flex-shrink-0 px-5 py-3 border-t border-gray-100 bg-white" style={{ paddingBottom: 'env(safe-area-inset-bottom, 12px)' }}>
        <button
          onClick={handleSubmit}
          disabled={!title.trim() || submitting}
          className={`w-full min-h-[50px] rounded-2xl text-base font-bold transition-all active:scale-[0.98] flex items-center justify-center gap-2 ${
            title.trim()
              ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
              : 'bg-gray-200 text-gray-400'
          }`}
        >
          {submitting ? <><Loader2 className="w-5 h-5 animate-spin" /> 登録中</> : '登録'}
        </button>
      </div>
    </div>
  );
}
