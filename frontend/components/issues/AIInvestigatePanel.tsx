'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, AIInvestigationResult } from '@/lib/issue_types';
import { Search, Zap, Shield, Wrench, Scale, Loader2, AlertCircle, RefreshCw, Check, X } from 'lucide-react';

interface AIInvestigatePanelProps {
  issue: Issue;
  onUpdated?: (issue: Issue) => void;
}

const BASE_MODES = [
  { type: 'rca' as const, label: '根本原因分析', icon: Search, desc: 'なぜなぜ分析で根本原因を特定' },
  { type: 'impact' as const, label: '影響分析', icon: Zap, desc: '未解決時の波及影響を分析' },
  { type: 'countermeasure' as const, label: '対策提案', icon: Shield, desc: '即効策と根本対策を提案' },
];

const ADVANCED_MODES = [
  { type: 'technical' as const, label: '技術解説', icon: Wrench, desc: '技術コンテキスト・基準参照' },
  { type: 'legal' as const, label: '法的リスク', icon: Scale, desc: '契約・法規制リスク評価' },
];

type InvestigateType = 'rca' | 'impact' | 'countermeasure' | 'technical' | 'legal';

export default function AIInvestigatePanel({ issue, onUpdated }: AIInvestigatePanelProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AIInvestigationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  async function investigate(type: InvestigateType) {
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

  async function confirmLegalRisk(level: 'high' | 'medium' | 'low') {
    setConfirming(true);
    try {
      const res = await authFetch(`/api/issues/${issue.id}/confirm-legal-risk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ legal_risk_level: level }),
      });
      if (res.ok) {
        const updated = await res.json();
        onUpdated?.(updated);
      }
    } catch (e) {
      // Silently fail, badge will just not appear
    } finally {
      setConfirming(false);
    }
  }

  const allModes = [...BASE_MODES, ...ADVANCED_MODES];
  const RISK_COLORS: Record<string, string> = {
    high: 'bg-red-100 text-red-700',
    medium: 'bg-yellow-100 text-yellow-700',
    low: 'bg-green-100 text-green-700',
  };

  return (
    <div>
      <label className="text-xs font-medium text-gray-500 block mb-2">AI調査</label>

      {/* 基本モード */}
      <div className="flex flex-wrap gap-1 mb-1">
        {BASE_MODES.map((mode) => (
          <button
            key={mode.type}
            onClick={() => investigate(mode.type)}
            disabled={loading}
            className="flex flex-col items-center gap-1 p-2 border border-gray-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-1 min-w-[80px]"
          >
            <mode.icon size={16} className="text-blue-600" />
            <span className="text-[10px] font-medium text-gray-700 leading-tight text-center">{mode.label}</span>
          </button>
        ))}
      </div>

      {/* 技術・法務モード */}
      <div className="flex flex-wrap gap-1 mb-3">
        {ADVANCED_MODES.map((mode) => (
          <button
            key={mode.type}
            onClick={() => investigate(mode.type)}
            disabled={loading}
            className="flex flex-col items-center gap-1 p-2 border border-gray-200 rounded-lg hover:bg-purple-50 hover:border-purple-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-1 min-w-[80px]"
          >
            <mode.icon size={16} className="text-purple-600" />
            <span className="text-[10px] font-medium text-gray-700 leading-tight text-center">{mode.label}</span>
          </button>
        ))}
      </div>

      {/* ローディング状態 */}
      {loading && (
        <div className="flex items-center gap-2 p-3 bg-blue-50 rounded-lg">
          <Loader2 size={16} className="text-blue-600 animate-spin" />
          <span className="text-xs text-blue-700">AI分析中...（約10秒）</span>
        </div>
      )}

      {/* エラー状態 */}
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
              {allModes.find((m) => m.type === result.type)?.label}
            </span>
            <span className="text-[10px] text-gray-400">
              関連{result.related_issue_ids.length}件
            </span>
          </div>
          <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">{result.result}</p>

          {/* Legal mode: confirm/reject UI */}
          {result.type === 'legal' && result.suggested_level && (
            <div className="mt-2 pt-2 border-t border-gray-200">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[10px] text-gray-500">判定:</span>
                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${RISK_COLORS[result.suggested_level] || ''}`}>
                  {result.suggested_level}
                </span>
                {!confirming && (
                  <>
                    <button
                      onClick={() => confirmLegalRisk(result.suggested_level!)}
                      className="flex items-center gap-0.5 text-[10px] text-green-600 hover:text-green-700 px-1.5 py-0.5 rounded border border-green-200 hover:bg-green-50"
                    >
                      <Check size={10} /> 確定
                    </button>
                    <button
                      onClick={() => setResult(null)}
                      className="flex items-center gap-0.5 text-[10px] text-gray-400 hover:text-gray-600 px-1.5 py-0.5 rounded border border-gray-200 hover:bg-gray-50"
                    >
                      <X size={10} /> 却下
                    </button>
                  </>
                )}
                {confirming && <Loader2 size={12} className="text-green-600 animate-spin" />}
              </div>

              {/* Evidence recommendations */}
              {result.evidence_recommendations && result.evidence_recommendations.length > 0 && (
                <div className="mt-1">
                  <span className="text-[9px] text-gray-500 block mb-0.5">推奨エビデンス:</span>
                  <div className="flex flex-wrap gap-1">
                    {result.evidence_recommendations.map((rec, i) => (
                      <span key={i} className="text-[9px] bg-orange-50 text-orange-700 px-1.5 py-0.5 rounded">
                        {rec}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Disclaimer */}
              <p className="text-[9px] text-gray-400 mt-1.5">AI助言であり法的助言ではありません</p>
            </div>
          )}

          {/* Sources for technical/legal */}
          {result.sources && result.sources.length > 0 && (
            <div className="mt-1.5 pt-1.5 border-t border-gray-200">
              <span className="text-[9px] text-gray-500 block mb-0.5">参照:</span>
              {result.sources.map((s, i) => (
                <span key={i} className="text-[9px] text-blue-500 block truncate" title={s.rel_path}>
                  {s.title || s.rel_path}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
