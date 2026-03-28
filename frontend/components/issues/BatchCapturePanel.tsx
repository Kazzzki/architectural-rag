'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, BatchCaptureResponse } from '@/lib/issue_types';
import { Zap, Check, X, Loader2, FileText } from 'lucide-react';

const CATEGORY_COLORS: Record<string, string> = {
  '工程': 'bg-blue-100 text-blue-700',
  'コスト': 'bg-orange-100 text-orange-700',
  '品質': 'bg-green-100 text-green-700',
  '安全': 'bg-red-100 text-red-700',
};

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-red-500 text-white',
  normal: 'bg-blue-100 text-blue-700',
  minor: 'bg-gray-100 text-gray-600',
};

export default function BatchCapturePanel({
  projectName,
  onComplete,
  onClose,
}: {
  projectName: string;
  onComplete: (issues: Issue[]) => void;
  onClose: () => void;
}) {
  const [memoText, setMemoText] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [extracted, setExtracted] = useState<Issue[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleExtract() {
    if (!memoText.trim()) return;
    setExtracting(true);
    setError('');
    try {
      const res = await authFetch('/api/issues/capture-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: memoText, project_name: projectName }),
      });
      if (!res.ok) throw new Error('抽出に失敗しました');
      const data: BatchCaptureResponse = await res.json();
      setExtracted(data.issues);
      setSelected(new Set(data.issues.map((iss) => iss.id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : '抽出エラー');
    } finally {
      setExtracting(false);
    }
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleDone() {
    if (!extracted) return;
    const accepted = extracted.filter((iss) => selected.has(iss.id));
    onComplete(accepted);
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col">
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-blue-600" />
            <h2 className="text-base font-semibold text-gray-800">会議メモから一括登録</h2>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {!extracted ? (
            /* 入力フェーズ */
            <>
              <p className="text-sm text-gray-500">
                打ち合わせメモを貼り付けてください。AIが課題を自動抽出します。
              </p>
              <textarea
                value={memoText}
                onChange={(e) => setMemoText(e.target.value)}
                placeholder="例: 3階の配管ルートが設計変更により再検討が必要。外壁タイルの納期が2週間遅延。安全帯の使用率が低下している..."
                className="w-full h-48 text-sm border border-gray-300 rounded-xl px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
              />
              {error && <p className="text-sm text-red-500">{error}</p>}
              <button
                onClick={handleExtract}
                disabled={!memoText.trim() || extracting}
                className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-40 transition-colors"
              >
                {extracting ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    AI抽出中…
                  </>
                ) : (
                  <>
                    <FileText size={16} />
                    課題を抽出
                  </>
                )}
              </button>
            </>
          ) : (
            /* プレビューフェーズ */
            <>
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-600">
                  <span className="font-semibold text-blue-600">{extracted.length}件</span>の課題を抽出しました。
                  登録する課題を選択してください。
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setSelected(new Set(extracted.map((iss) => iss.id)))}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    全選択
                  </button>
                  <button
                    onClick={() => setSelected(new Set())}
                    className="text-xs text-gray-500 hover:underline"
                  >
                    全解除
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                {extracted.map((iss) => (
                  <button
                    key={iss.id}
                    onClick={() => toggleSelect(iss.id)}
                    className={`w-full flex items-start gap-3 px-4 py-3 rounded-xl border transition-colors text-left ${
                      selected.has(iss.id)
                        ? 'border-blue-400 bg-blue-50'
                        : 'border-gray-200 bg-white hover:bg-gray-50'
                    }`}
                  >
                    <div className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 ${
                      selected.has(iss.id)
                        ? 'bg-blue-600 border-blue-600'
                        : 'border-gray-300'
                    }`}>
                      {selected.has(iss.id) && <Check size={14} className="text-white" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-gray-800 truncate">{iss.title}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${CATEGORY_COLORS[iss.category] || ''}`}>
                          {iss.category}
                        </span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${PRIORITY_BADGE[iss.priority] || ''}`}>
                          {iss.priority}
                        </span>
                      </div>
                      {iss.description && (
                        <p className="text-xs text-gray-500 truncate">{iss.description}</p>
                      )}
                    </div>
                  </button>
                ))}
              </div>

              {extracted.length === 0 && (
                <div className="text-center py-8 text-sm text-gray-400">
                  課題が見つかりませんでした。メモの内容を確認してください。
                </div>
              )}
            </>
          )}
        </div>

        {/* フッター */}
        {extracted && extracted.length > 0 && (
          <div className="px-5 py-4 border-t border-gray-100 flex items-center justify-between">
            <button
              onClick={() => { setExtracted(null); setSelected(new Set()); }}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              メモを再入力
            </button>
            <button
              onClick={handleDone}
              disabled={selected.size === 0 || saving}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-40 transition-colors"
            >
              <Check size={16} />
              {selected.size}件を登録済み
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
