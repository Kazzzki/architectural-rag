'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { ChainRiskScanResult } from '@/lib/issue_types';
import { X, Loader2, AlertTriangle, Scale, FileWarning, CheckCircle } from 'lucide-react';

interface ChainRiskScanPanelProps {
  issueId: string;
  onClose: () => void;
  onNodeHighlight?: (issueId: string) => void;
}

const SEVERITY_COLORS: Record<string, string> = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  low: 'bg-green-100 text-green-700 border-green-200',
};

type LoadingStage = 'chain' | 'rag' | 'analysis' | 'done';

const STAGE_LABELS: Record<LoadingStage, string> = {
  chain: '因果チェーン取得中...',
  rag: 'RAG検索中...',
  analysis: 'AI分析中...',
  done: '',
};

export default function ChainRiskScanPanel({ issueId, onClose, onNodeHighlight }: ChainRiskScanPanelProps) {
  const [result, setResult] = useState<ChainRiskScanResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<LoadingStage>('chain');
  const [warning, setWarning] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function scan() {
      setLoading(true);
      setError(null);
      setResult(null);
      setWarning(null);

      // Progressive loading simulation
      setStage('chain');
      await new Promise(r => setTimeout(r, 500));
      if (cancelled) return;
      setStage('rag');
      await new Promise(r => setTimeout(r, 500));
      if (cancelled) return;
      setStage('analysis');

      try {
        const res = await authFetch(`/api/issues/${issueId}/chain-risk-scan`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!cancelled) {
          if (data.warning) setWarning(data.warning);
          setResult(data);
          setStage('done');
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'チェーンリスク分析に失敗しました');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    scan();
    return () => { cancelled = true; };
  }, [issueId]);

  const totalFindings = result
    ? result.technical_risks.length + result.legal_risks.length + result.evidence_gaps.length
    : 0;

  return (
    <div className="fixed right-0 top-0 h-full w-80 md:w-96 bg-white border-l border-gray-200 shadow-xl z-50 flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="p-4 border-b border-gray-100 flex items-center justify-between flex-shrink-0">
        <div>
          <h3 className="text-sm font-bold text-gray-800">チェーンリスク分析</h3>
          {result && (
            <span className="text-[10px] text-gray-500">
              {result.scanned_issue_ids.length}件の課題を分析 / {totalFindings}件の発見
            </span>
          )}
        </div>
        <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">
          <X size={16} />
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 p-6">
          <Loader2 size={24} className="text-blue-600 animate-spin" />
          <span className="text-sm text-blue-700">{STAGE_LABELS[stage]}</span>
          <div className="flex gap-1.5">
            {(['chain', 'rag', 'analysis'] as const).map((s) => (
              <div
                key={s}
                className={`w-2 h-2 rounded-full ${
                  s === stage ? 'bg-blue-500 animate-pulse' :
                  (['chain', 'rag', 'analysis'].indexOf(s) < ['chain', 'rag', 'analysis'].indexOf(stage)) ? 'bg-blue-500' : 'bg-gray-200'
                }`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="p-4">
          <div className="flex items-center gap-2 p-3 bg-red-50 rounded-lg">
            <AlertTriangle size={16} className="text-red-500" />
            <span className="text-xs text-red-700">{error}</span>
          </div>
        </div>
      )}

      {/* Warning */}
      {warning && (
        <div className="px-4 pt-2">
          <div className="flex items-center gap-2 p-2 bg-yellow-50 rounded-lg">
            <AlertTriangle size={14} className="text-yellow-600" />
            <span className="text-[10px] text-yellow-700">{warning}</span>
          </div>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Technical Risks */}
          {result.technical_risks.length > 0 && (
            <section>
              <h4 className="text-xs font-medium text-gray-600 mb-2 flex items-center gap-1">
                <AlertTriangle size={12} className="text-orange-500" /> 技術リスク
              </h4>
              <div className="space-y-1.5">
                {result.technical_risks.map((r, i) => (
                  <div key={i} className={`p-2 rounded-lg border ${SEVERITY_COLORS[r.severity] || SEVERITY_COLORS.medium}`}>
                    <div className="flex items-start justify-between gap-1">
                      <p className="text-[11px] leading-relaxed flex-1">{r.risk}</p>
                      <span className="text-[9px] font-medium flex-shrink-0">{r.severity}</span>
                    </div>
                    <button
                      onClick={() => onNodeHighlight?.(r.issue_id)}
                      className="text-[9px] text-blue-500 hover:underline mt-0.5"
                    >
                      {r.issue_id.slice(0, 8)}...
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Legal Risks */}
          {result.legal_risks.length > 0 && (
            <section>
              <h4 className="text-xs font-medium text-gray-600 mb-2 flex items-center gap-1">
                <Scale size={12} className="text-red-500" /> 法的リスク
              </h4>
              <div className="space-y-1.5">
                {result.legal_risks.map((r, i) => (
                  <div key={i} className="p-2 rounded-lg border bg-red-50 text-red-700 border-red-200">
                    <p className="text-[11px] leading-relaxed">{r.risk}</p>
                    {r.law_reference && (
                      <span className="text-[9px] text-red-500 block mt-0.5">{r.law_reference}</span>
                    )}
                    <button
                      onClick={() => onNodeHighlight?.(r.issue_id)}
                      className="text-[9px] text-blue-500 hover:underline mt-0.5"
                    >
                      {r.issue_id.slice(0, 8)}...
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Evidence Gaps */}
          {result.evidence_gaps.length > 0 && (
            <section>
              <h4 className="text-xs font-medium text-gray-600 mb-2 flex items-center gap-1">
                <FileWarning size={12} className="text-orange-500" /> エビデンスギャップ
              </h4>
              <div className="space-y-1.5">
                {result.evidence_gaps.map((r, i) => (
                  <div key={i} className={`p-2 rounded-lg border ${SEVERITY_COLORS[r.urgency] || SEVERITY_COLORS.medium}`}>
                    <p className="text-[11px] leading-relaxed">{r.gap}</p>
                    <button
                      onClick={() => onNodeHighlight?.(r.issue_id)}
                      className="text-[9px] text-blue-500 hover:underline mt-0.5"
                    >
                      {r.issue_id.slice(0, 8)}...
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Recommended Actions */}
          {result.recommended_actions.length > 0 && (
            <section>
              <h4 className="text-xs font-medium text-gray-600 mb-2 flex items-center gap-1">
                <CheckCircle size={12} className="text-green-500" /> 推奨アクション
              </h4>
              <div className="space-y-1.5">
                {result.recommended_actions.map((r, i) => (
                  <div key={i} className={`p-2 rounded-lg border ${SEVERITY_COLORS[r.priority] || SEVERITY_COLORS.medium}`}>
                    <p className="text-[11px] leading-relaxed">{r.action}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Empty state */}
          {totalFindings === 0 && (
            <div className="text-center py-8">
              <CheckCircle size={24} className="text-green-400 mx-auto mb-2" />
              <p className="text-sm text-gray-500">リスクは検出されませんでした</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
