'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { DashboardSummary, Issue } from '@/lib/issue_types';
import { BarChart3, AlertTriangle, Clock, Users, TrendingUp, Zap } from 'lucide-react';

const STATUS_COLORS: Record<string, string> = {
  '発生中': 'bg-red-100 text-red-700',
  '対応中': 'bg-yellow-100 text-yellow-700',
  '解決済み': 'bg-green-100 text-green-700',
};

const PRIORITY_LABELS: Record<string, { label: string; color: string }> = {
  critical: { label: 'Critical', color: 'bg-red-500 text-white' },
  normal: { label: 'Normal', color: 'bg-blue-100 text-blue-700' },
  minor: { label: 'Minor', color: 'bg-gray-100 text-gray-600' },
};

const CATEGORY_COLORS: Record<string, string> = {
  '工程': 'bg-blue-100 text-blue-700 border-blue-200',
  'コスト': 'bg-orange-100 text-orange-700 border-orange-200',
  '品質': 'bg-green-100 text-green-700 border-green-200',
  '安全': 'bg-red-100 text-red-700 border-red-200',
};

export default function DashboardPanel({
  projectName,
  onSelectIssue,
  onStartReview,
  onStartBatchCapture,
}: {
  projectName: string;
  onSelectIssue: (issue: Issue) => void;
  onStartReview: () => void;
  onStartBatchCapture: () => void;
}) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    authFetch(`/api/issues/${encodeURIComponent(projectName)}/dashboard-summary`)
      .then((r) => r.json())
      .then((data: DashboardSummary) => setSummary(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectName]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-sm text-gray-400">読み込み中…</span>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-sm text-gray-400">データの取得に失敗しました</span>
      </div>
    );
  }

  const unresolvedCount = (summary.status_counts['発生中'] || 0) + (summary.status_counts['対応中'] || 0);

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 max-w-4xl mx-auto w-full space-y-6">
      {/* アクションボタン */}
      <div className="flex gap-3">
        <button
          onClick={onStartBatchCapture}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Zap size={16} />
          会議メモから一括登録
        </button>
        {unresolvedCount > 0 && (
          <button
            onClick={onStartReview}
            className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-300 text-gray-700 rounded-xl text-sm font-medium hover:bg-gray-50 transition-colors"
          >
            <TrendingUp size={16} />
            クイックレビュー（{unresolvedCount}件）
          </button>
        )}
      </div>

      {/* 統計カード */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 size={16} className="text-gray-400" />
            <span className="text-xs text-gray-500">合計課題数</span>
          </div>
          <div className="text-2xl font-bold text-gray-800">{summary.total}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-red-400" />
            <span className="text-xs text-gray-500">Critical</span>
          </div>
          <div className="text-2xl font-bold text-red-600">{summary.priority_counts.critical || 0}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Clock size={16} className="text-yellow-500" />
            <span className="text-xs text-gray-500">未対応</span>
          </div>
          <div className="text-2xl font-bold text-yellow-600">{unresolvedCount}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Users size={16} className="text-blue-400" />
            <span className="text-xs text-gray-500">担当者数</span>
          </div>
          <div className="text-2xl font-bold text-blue-600">
            {Object.keys(summary.assignee_counts).filter((k) => k !== '未割当').length}
          </div>
        </div>
      </div>

      {/* ステータス分布・カテゴリ分布 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* ステータス分布 */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">ステータス分布</h3>
          <div className="space-y-2">
            {Object.entries(summary.status_counts).map(([status, count]) => (
              <div key={status} className="flex items-center gap-3">
                <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[status] || 'bg-gray-100 text-gray-600'}`}>
                  {status}
                </span>
                <div className="flex-1 bg-gray-100 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${status === '発生中' ? 'bg-red-400' : status === '対応中' ? 'bg-yellow-400' : 'bg-green-400'}`}
                    style={{ width: `${summary.total ? (count / summary.total) * 100 : 0}%` }}
                  />
                </div>
                <span className="text-sm font-medium text-gray-600 w-8 text-right">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* カテゴリ分布 */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">カテゴリ分布</h3>
          <div className="space-y-2">
            {Object.entries(summary.category_counts).map(([cat, count]) => (
              <div key={cat} className="flex items-center gap-3">
                <span className={`text-xs px-2 py-0.5 rounded-full border ${CATEGORY_COLORS[cat] || 'bg-gray-100 text-gray-600'}`}>
                  {cat}
                </span>
                <div className="flex-1 bg-gray-100 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${cat === '工程' ? 'bg-blue-400' : cat === 'コスト' ? 'bg-orange-400' : cat === '品質' ? 'bg-green-400' : 'bg-red-400'}`}
                    style={{ width: `${summary.total ? (count / summary.total) * 100 : 0}%` }}
                  />
                </div>
                <span className="text-sm font-medium text-gray-600 w-8 text-right">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 担当者別 */}
      {Object.keys(summary.assignee_counts).length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">担当者別課題数</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(summary.assignee_counts)
              .sort(([, a], [, b]) => b - a)
              .map(([assignee, count]) => (
                <span
                  key={assignee}
                  className={`text-xs px-3 py-1.5 rounded-lg border ${
                    assignee === '未割当'
                      ? 'bg-gray-50 text-gray-500 border-gray-200'
                      : 'bg-blue-50 text-blue-700 border-blue-200'
                  }`}
                >
                  {assignee}: {count}件
                </span>
              ))}
          </div>
        </div>
      )}

      {/* 要対応リスト */}
      {summary.needs_action.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            <AlertTriangle size={14} className="inline mr-1 text-orange-500" />
            要対応（{summary.needs_action.length}件）
          </h3>
          <div className="space-y-1.5">
            {summary.needs_action.map((iss) => (
              <button
                key={iss.id}
                onClick={() => onSelectIssue(iss)}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
              >
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${PRIORITY_LABELS[iss.priority]?.color || 'bg-gray-100'}`}>
                  {iss.priority === 'critical' ? '!' : iss.priority === 'normal' ? '-' : '·'}
                </span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${CATEGORY_COLORS[iss.category] || ''}`}>
                  {iss.category}
                </span>
                <span className="text-sm text-gray-800 truncate flex-1">{iss.title}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_COLORS[iss.status] || ''}`}>
                  {iss.status}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 最近の課題 */}
      {summary.recent_issues.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            <Clock size={14} className="inline mr-1 text-blue-500" />
            直近7日の課題（{summary.recent_issues.length}件）
          </h3>
          <div className="space-y-1.5">
            {summary.recent_issues.map((iss) => (
              <button
                key={iss.id}
                onClick={() => onSelectIssue(iss)}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
              >
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${CATEGORY_COLORS[iss.category] || ''}`}>
                  {iss.category}
                </span>
                <span className="text-sm text-gray-800 truncate flex-1">{iss.title}</span>
                <span className="text-[10px] text-gray-400">
                  {new Date(iss.created_at).toLocaleDateString('ja-JP', { month: 'short', day: 'numeric' })}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
