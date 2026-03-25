'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, HealthCheckResult } from '@/lib/issue_types';
import { Activity, AlertTriangle, Link2, RotateCw, Loader2, AlertCircle, RefreshCw, X } from 'lucide-react';

interface HealthCheckPanelProps {
  projectName: string;
  onClose: () => void;
  onSelectIssue: (issue: Issue) => void;
}

export default function HealthCheckPanel({ projectName, onClose, onSelectIssue }: HealthCheckPanelProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HealthCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runCheck() {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`/api/issues/${encodeURIComponent(projectName)}/health-check`, {
        method: 'POST',
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : '健全性チェックに失敗しました');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed z-50 flex flex-col bg-white shadow-2xl right-0 top-0 h-full w-80 border-l border-gray-200">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-blue-600" />
          <span className="text-sm font-semibold text-gray-800">グラフ健全性チェック</span>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1">
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {!result && !loading && !error && (
          <div className="text-center py-8">
            <Activity size={32} className="text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-500 mb-4">
              グラフの健全性をチェックします。孤立ノード、因果ループ、未解決のCritical課題を検出し、AIが見落とされた因果関係を提案します。
            </p>
            <button
              onClick={runCheck}
              className="text-sm bg-blue-600 text-white rounded-lg px-6 py-2 hover:bg-blue-700"
            >
              チェック開始
            </button>
          </div>
        )}

        {/* ローディング — 統一非同期パターン */}
        {loading && (
          <div className="flex items-center gap-2 p-3 bg-blue-50 rounded-lg">
            <Loader2 size={16} className="text-blue-600 animate-spin" />
            <span className="text-xs text-blue-700">分析中...（約10秒）</span>
          </div>
        )}

        {/* エラー — 統一非同期パターン */}
        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 rounded-lg">
            <AlertCircle size={16} className="text-red-500" />
            <span className="text-xs text-red-700 flex-1">{error}</span>
            <button onClick={runCheck} className="text-red-600 hover:text-red-700 p-0.5">
              <RefreshCw size={14} />
            </button>
          </div>
        )}

        {/* 結果 */}
        {result && !loading && (
          <>
            {/* サマリー */}
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-orange-50 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-orange-600">{result.orphans?.length ?? 0}</div>
                <div className="text-[10px] text-orange-500">孤立ノード</div>
              </div>
              <div className="bg-red-50 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-red-600">{result.loops?.length ?? 0}</div>
                <div className="text-[10px] text-red-500">ループ</div>
              </div>
              <div className="bg-yellow-50 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-yellow-600">{result.unresolved_criticals?.length ?? 0}</div>
                <div className="text-[10px] text-yellow-600">未解決Critical</div>
              </div>
            </div>

            {/* 孤立ノード */}
            {result.orphans && result.orphans.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <Link2 size={13} className="text-orange-500" />
                  <span className="text-xs font-medium text-gray-700">孤立ノード</span>
                </div>
                <div className="space-y-1">
                  {result.orphans.map((iss: Issue) => (
                    <button
                      key={iss.id}
                      onClick={() => onSelectIssue(iss)}
                      className="w-full text-left text-xs px-2 py-1.5 bg-orange-50 rounded hover:bg-orange-100 transition-colors truncate"
                    >
                      {iss.title}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* ループ */}
            {result.loops && result.loops.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <RotateCw size={13} className="text-red-500" />
                  <span className="text-xs font-medium text-gray-700">因果ループ</span>
                </div>
                <div className="space-y-1">
                  {result.loops.map((loop: string[], i: number) => (
                    <div key={i} className="text-xs px-2 py-1.5 bg-red-50 rounded">
                      {loop.join(' → ')} → (循環)
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 未解決Critical */}
            {result.unresolved_criticals && result.unresolved_criticals.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <AlertTriangle size={13} className="text-yellow-500" />
                  <span className="text-xs font-medium text-gray-700">未解決Critical</span>
                </div>
                <div className="space-y-1">
                  {result.unresolved_criticals.map((iss: Issue) => (
                    <button
                      key={iss.id}
                      onClick={() => onSelectIssue(iss)}
                      className="w-full text-left text-xs px-2 py-1.5 bg-yellow-50 rounded hover:bg-yellow-100 transition-colors truncate"
                    >
                      {iss.title} ({iss.status})
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* AIサジェスト */}
            {result.ai_suggestions && result.ai_suggestions.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <Activity size={13} className="text-violet-500" />
                  <span className="text-xs font-medium text-gray-700">AIが提案する因果関係</span>
                </div>
                <div className="space-y-1">
                  {result.ai_suggestions.map((s: { from_title?: string; to_title?: string; reason?: string }, i: number) => (
                    <div key={i} className="text-xs px-2 py-1.5 bg-violet-50 rounded">
                      <span className="font-medium">{s.from_title}</span>
                      <span className="text-gray-400 mx-1">→</span>
                      <span className="font-medium">{s.to_title}</span>
                      {s.reason && <span className="text-gray-500 ml-1">({s.reason})</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 再チェックボタン */}
            <button
              onClick={runCheck}
              disabled={loading}
              className="w-full text-xs border border-gray-200 rounded-lg py-2 hover:bg-gray-50 text-gray-600"
            >
              再チェック
            </button>
          </>
        )}
      </div>
    </div>
  );
}
