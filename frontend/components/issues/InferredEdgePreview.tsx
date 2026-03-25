'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { InferredEdge } from '@/lib/issue_types';
import { Check, X, Loader2, AlertCircle, Sparkles } from 'lucide-react';

interface InferredEdgePreviewProps {
  issueIds: string[];
  issues: { id: string; title: string }[];
  onEdgeAccepted: () => void;
  onClose: () => void;
}

export default function InferredEdgePreview({
  issueIds, issues, onEdgeAccepted, onClose,
}: InferredEdgePreviewProps) {
  const [loading, setLoading] = useState(false);
  const [edges, setEdges] = useState<InferredEdge[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [acceptedIds, setAcceptedIds] = useState<Set<string>>(new Set());

  const titleMap = Object.fromEntries(issues.map((i) => [i.id, i.title]));

  async function runInference() {
    setLoading(true);
    setError(null);
    setStarted(true);
    try {
      const res = await authFetch('/api/issues/ai-infer-causation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_ids: issueIds }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setEdges(data.inferred_edges || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AI推定に失敗しました');
    } finally {
      setLoading(false);
    }
  }

  async function acceptEdge(edge: InferredEdge) {
    try {
      const res = await authFetch('/api/issues/edges/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_id: edge.from_id,
          to_id: edge.to_id,
          confirmed: true,
        }),
      });
      if (res.ok) {
        setAcceptedIds((prev) => new Set([...prev, `${edge.from_id}-${edge.to_id}`]));
        // エッジにラベルを設定
        if (edge.suggested_label) {
          const data = await res.json();
          if (data.edge_id) {
            await authFetch(`/api/issues/edges/${data.edge_id}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ label: edge.suggested_label, relation_type: 'direct_cause' }),
            });
          }
        }
        onEdgeAccepted();
      }
    } catch {}
  }

  if (!started) {
    return (
      <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-30 bg-white border border-violet-200 rounded-xl shadow-xl p-4 min-w-[300px]">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-violet-600" />
            <span className="text-sm font-medium text-gray-800">AI因果推定</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={16} />
          </button>
        </div>
        <p className="text-xs text-gray-500 mb-3">
          選択した{issueIds.length}件のノード間に隠れた因果関係がないかAIが分析します。
        </p>
        <button
          onClick={runInference}
          className="w-full text-sm bg-violet-600 text-white rounded-lg py-2 hover:bg-violet-700"
        >
          推定を開始
        </button>
      </div>
    );
  }

  return (
    <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-30 bg-white border border-violet-200 rounded-xl shadow-xl p-4 min-w-[340px] max-w-[420px]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-violet-600" />
          <span className="text-sm font-medium text-gray-800">AI因果推定結果</span>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <X size={16} />
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 p-3 bg-violet-50 rounded-lg">
          <Loader2 size={16} className="text-violet-600 animate-spin" />
          <span className="text-xs text-violet-700">AI分析中...（約10秒）</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 rounded-lg">
          <AlertCircle size={16} className="text-red-500" />
          <span className="text-xs text-red-700">{error}</span>
        </div>
      )}

      {!loading && !error && edges.length === 0 && (
        <div className="text-xs text-gray-500 text-center py-3">
          隠れた因果関係は見つかりませんでした。
        </div>
      )}

      {!loading && edges.length > 0 && (
        <div className="space-y-2">
          {edges.map((edge, i) => {
            const key = `${edge.from_id}-${edge.to_id}`;
            const accepted = acceptedIds.has(key);
            return (
              <div key={i} className={`flex items-start gap-2 p-2 rounded-lg border transition-colors ${accepted ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'}`}>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-gray-800">
                    {titleMap[edge.from_id] || edge.from_id.slice(0, 8)} → {titleMap[edge.to_id] || edge.to_id.slice(0, 8)}
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    {edge.reason} (確信度: {Math.round(edge.confidence * 100)}%)
                  </div>
                  {edge.suggested_label && (
                    <div className="text-[10px] text-violet-600 mt-0.5">
                      ラベル: {edge.suggested_label}
                    </div>
                  )}
                </div>
                {accepted ? (
                  <span className="text-green-600 text-xs flex items-center gap-0.5"><Check size={14} /> 承認済</span>
                ) : (
                  <div className="flex gap-1 flex-shrink-0">
                    <button
                      onClick={() => acceptEdge(edge)}
                      className="text-green-600 hover:bg-green-100 p-1 rounded"
                      title="承認"
                    >
                      <Check size={16} />
                    </button>
                    <button
                      onClick={() => setEdges((prev) => prev.filter((_, idx) => idx !== i))}
                      className="text-gray-400 hover:bg-gray-100 p-1 rounded"
                      title="却下"
                    >
                      <X size={16} />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
