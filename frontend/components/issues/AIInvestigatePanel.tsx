'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, AIInvestigationResult } from '@/lib/issue_types';
import { Search, Zap, Shield, Loader2, AlertCircle, RefreshCw } from 'lucide-react';

interface AIInvestigatePanelProps {
  issue: Issue;
}

const MODES = [
  { type: 'rca' as const, label: '根本原因分析', icon: Search, desc: 'なぜなぜ分析で根本原因を特定' },
  { type: 'impact' as const, label: '影響分析', icon: Zap, desc: '未解決時の波及影響を分析' },
  { type: 'countermeasure' as const, label: '対策提案', icon: Shield, desc: '即効策と根本対策を提案' },
];

export default function AIInvestigatePanel({ issue }: AIInvestigatePanelProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AIInvestigationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function investigate(type: 'rca' | 'impact' | 'countermeasure') {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await authFetch(`/api/issues/${issue.id}/ai-investigate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data: AIInvestigationResult = await res.json();
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AI分析に失敗しました');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <label className="text-xs font-medium text-gray-500 block mb-2">AI調査</label>

      {/* モード選択ボタン */}
      <div className="grid grid-cols-3 gap-1 mb-3">
        {MODES.map((mode) => (
          <button
            key={mode.type}
            onClick={() => investigate(mode.type)}
            disabled={loading}
            className="flex flex-col items-center gap-1 p-2 border border-gray-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <mode.icon size={16} className="text-blue-600" />
            <span className="text-[10px] font-medium text-gray-700 leading-tight text-center">{mode.label}</span>
          </button>
        ))}
      </div>

      {/* ローディング状態 — 統一非同期パターン */}
      {loading && (
        <div className="flex items-center gap-2 p-3 bg-blue-50 rounded-lg">
          <Loader2 size={16} className="text-blue-600 animate-spin" />
          <span className="text-xs text-blue-700">AI分析中...（約10秒）</span>
        </div>
      )}

      {/* エラー状態 — 統一非同期パターン */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 rounded-lg">
          <AlertCircle size={16} className="text-red-500" />
          <span className="text-xs text-red-700 flex-1">{error}</span>
          <button
            onClick={() => result ? investigate(result.type) : setError(null)}
            className="text-red-600 hover:text-red-700 p-0.5"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      )}

      {/* 結果表示 */}
      {result && !loading && (
        <div className="p-3 bg-gray-50 rounded-lg animate-in fade-in duration-300">
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="text-[10px] font-medium text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded">
              {MODES.find((m) => m.type === result.type)?.label}
            </span>
            <span className="text-[10px] text-gray-400">
              関連{result.related_issue_ids.length}件
            </span>
          </div>
          <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">{result.result}</p>
        </div>
      )}
    </div>
  );
}
