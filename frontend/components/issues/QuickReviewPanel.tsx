'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue } from '@/lib/issue_types';
import { ChevronRight, Check, AlertTriangle, ArrowRight, X, User, Flag } from 'lucide-react';

const CATEGORY_COLORS: Record<string, string> = {
  '工程': 'border-blue-400 bg-blue-50',
  'コスト': 'border-orange-400 bg-orange-50',
  '品質': 'border-green-400 bg-green-50',
  '安全': 'border-red-400 bg-red-50',
};

const STATUS_OPTIONS = ['発生中', '対応中', '解決済み'] as const;
const PRIORITY_OPTIONS = ['critical', 'normal', 'minor'] as const;

const PRIORITY_LABELS: Record<string, string> = {
  critical: 'Critical',
  normal: 'Normal',
  minor: 'Minor',
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500 text-white',
  normal: 'bg-blue-100 text-blue-700',
  minor: 'bg-gray-100 text-gray-600',
};

export default function QuickReviewPanel({
  projectName,
  onClose,
  onRefresh,
}: {
  projectName: string;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [reviewed, setReviewed] = useState<{ id: string; action: string }[]>([]);
  const [members, setMembers] = useState<string[]>([]);

  useEffect(() => {
    Promise.all([
      authFetch(`/api/issues?project_name=${encodeURIComponent(projectName)}&status=発生中`)
        .then((r) => r.json())
        .then((data) => {
          const activeIssues = (data.issues || []) as Issue[];
          setIssues(activeIssues);
        }),
      authFetch(`/api/issues/members?project_name=${encodeURIComponent(projectName)}`)
        .then((r) => r.json())
        .then((data) => setMembers((data || []).map((m: { name: string }) => m.name)))
        .catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [projectName]);

  const current = issues[currentIndex];
  const isComplete = currentIndex >= issues.length;

  async function updateIssue(updates: Record<string, string>) {
    if (!current || updating) return;
    setUpdating(true);
    try {
      await authFetch(`/api/issues/${current.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      const actionLabel = Object.entries(updates)
        .map(([k, v]) => `${k}→${v}`)
        .join(', ');
      setReviewed((prev) => [...prev, { id: current.id, action: actionLabel }]);
      setCurrentIndex((prev) => prev + 1);
    } finally {
      setUpdating(false);
    }
  }

  function skipIssue() {
    setReviewed((prev) => [...prev, { id: current?.id || '', action: 'スキップ' }]);
    setCurrentIndex((prev) => prev + 1);
  }

  function handleClose() {
    if (reviewed.length > 0) onRefresh();
    onClose();
  }

  if (loading) {
    return (
      <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 backdrop-blur-sm">
        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <span className="text-sm text-gray-400">読み込み中…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[85vh] flex flex-col">
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Flag size={18} className="text-blue-600" />
            <h2 className="text-base font-semibold text-gray-800">クイックレビュー</h2>
            {!isComplete && (
              <span className="text-xs text-gray-400 ml-2">
                {currentIndex + 1} / {issues.length}
              </span>
            )}
          </div>
          <button onClick={handleClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {issues.length === 0 ? (
            <div className="text-center py-12">
              <Check size={40} className="mx-auto text-green-400 mb-3" />
              <p className="text-sm text-gray-600">レビュー対象の課題がありません</p>
              <p className="text-xs text-gray-400 mt-1">すべての課題が対応中または解決済みです</p>
            </div>
          ) : isComplete ? (
            /* 完了サマリー */
            <div className="space-y-4">
              <div className="text-center py-4">
                <Check size={40} className="mx-auto text-green-500 mb-3" />
                <p className="text-base font-semibold text-gray-800">レビュー完了</p>
                <p className="text-sm text-gray-500 mt-1">
                  {reviewed.filter((r) => r.action !== 'スキップ').length}件を更新、
                  {reviewed.filter((r) => r.action === 'スキップ').length}件をスキップ
                </p>
              </div>
              <div className="space-y-1.5">
                {reviewed.map((r, i) => {
                  const iss = issues.find((issue) => issue.id === r.id);
                  return (
                    <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 text-sm">
                      <span className="text-gray-800 truncate flex-1">{iss?.title || r.id}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${r.action === 'スキップ' ? 'bg-gray-200 text-gray-500' : 'bg-green-100 text-green-700'}`}>
                        {r.action}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            /* レビューカード */
            <div className={`border-2 rounded-2xl p-5 space-y-4 ${CATEGORY_COLORS[current.category] || 'border-gray-200'}`}>
              {/* タイトル・メタ */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${PRIORITY_COLORS[current.priority] || ''}`}>
                    {PRIORITY_LABELS[current.priority]}
                  </span>
                  <span className="text-xs text-gray-400">{current.category}</span>
                </div>
                <h3 className="text-lg font-bold text-gray-800">{current.title}</h3>
              </div>

              {/* 詳細 */}
              {current.description && (
                <div>
                  <p className="text-xs text-gray-400 mb-1">説明</p>
                  <p className="text-sm text-gray-700">{current.description}</p>
                </div>
              )}
              {current.cause && (
                <div>
                  <p className="text-xs text-gray-400 mb-1">原因</p>
                  <p className="text-sm text-gray-700">{current.cause}</p>
                </div>
              )}
              {current.impact && (
                <div>
                  <p className="text-xs text-gray-400 mb-1">影響</p>
                  <p className="text-sm text-gray-700">{current.impact}</p>
                </div>
              )}

              {/* アクションボタン */}
              <div className="space-y-3 pt-2">
                <p className="text-xs text-gray-500 font-medium">ステータス変更</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => updateIssue({ status: '対応中' })}
                    disabled={updating}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 bg-yellow-500 text-white rounded-xl text-sm font-medium hover:bg-yellow-600 disabled:opacity-40 transition-colors"
                  >
                    <ArrowRight size={14} />
                    対応中
                  </button>
                  <button
                    onClick={() => updateIssue({ status: '解決済み' })}
                    disabled={updating}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 bg-green-500 text-white rounded-xl text-sm font-medium hover:bg-green-600 disabled:opacity-40 transition-colors"
                  >
                    <Check size={14} />
                    解決済み
                  </button>
                </div>

                <p className="text-xs text-gray-500 font-medium">優先度変更</p>
                <div className="flex gap-2">
                  {PRIORITY_OPTIONS.map((p) => (
                    <button
                      key={p}
                      onClick={() => updateIssue({ priority: p })}
                      disabled={updating || current.priority === p}
                      className={`flex-1 px-3 py-2 rounded-xl text-xs font-medium transition-colors disabled:opacity-30 ${
                        current.priority === p
                          ? 'ring-2 ring-blue-400 ' + PRIORITY_COLORS[p]
                          : PRIORITY_COLORS[p] + ' hover:opacity-80'
                      }`}
                    >
                      {PRIORITY_LABELS[p]}
                    </button>
                  ))}
                </div>

                {/* 担当者割当 */}
                {members.length > 0 && !current.assignee && (
                  <>
                    <p className="text-xs text-gray-500 font-medium">担当者割当</p>
                    <div className="flex flex-wrap gap-2">
                      {members.map((name) => (
                        <button
                          key={name}
                          onClick={() => updateIssue({ assignee: name, status: '対応中' })}
                          disabled={updating}
                          className="flex items-center gap-1 px-3 py-1.5 border border-gray-200 rounded-lg text-xs text-gray-700 hover:bg-blue-50 hover:border-blue-300 transition-colors"
                        >
                          <User size={12} />
                          {name}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* フッター */}
        {!isComplete && issues.length > 0 && (
          <div className="px-5 py-4 border-t border-gray-100 flex items-center justify-between">
            <button
              onClick={skipIssue}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              スキップ
            </button>
            <div className="flex items-center gap-1">
              {issues.map((_, i) => (
                <div
                  key={i}
                  className={`w-2 h-2 rounded-full ${
                    i < currentIndex ? 'bg-green-400' : i === currentIndex ? 'bg-blue-500' : 'bg-gray-200'
                  }`}
                />
              ))}
            </div>
            <button
              onClick={skipIssue}
              className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700"
            >
              次へ <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
