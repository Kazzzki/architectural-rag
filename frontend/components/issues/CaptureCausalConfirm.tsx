'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { CausalCandidate, Issue } from '@/lib/issue_types';

interface CaptureCausalConfirmProps {
  newIssueId: string;
  candidates: CausalCandidate[];
  existingIssues: Issue[];
  onDone: () => void;
}

export default function CaptureCausalConfirm({
  newIssueId,
  candidates,
  existingIssues,
  onDone,
}: CaptureCausalConfirmProps) {
  const [showAlternative, setShowAlternative] = useState(false);
  const [done, setDone] = useState(false);

  async function confirmEdge(fromId: string, toId: string) {
    await authFetch('/api/issues/edges/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_id: fromId, to_id: toId, confirmed: true }),
    });
    setDone(true);
    onDone();
  }

  function dismiss() {
    setDone(true);
    onDone();
  }

  if (done || candidates.length === 0) return null;

  return (
    <div className="border border-yellow-400 bg-yellow-50 rounded-2xl p-4 space-y-3">
      <div className="text-sm font-semibold text-yellow-800">AIが因果関係の候補を検出しました</div>

      {candidates.map((c) => {
        const existing = existingIssues.find((iss) => iss.id === c.issue_id);
        const existingTitle = existing?.title ?? c.issue_id;
        const isCauseOfNew = c.direction === 'cause_of_new';
        const label = isCauseOfNew
          ? `「${existingTitle}」が原因の可能性があります`
          : `「${existingTitle}」に影響する可能性があります`;

        return (
          <div key={c.issue_id} className="space-y-2">
            <div style={{ fontSize: 15 }} className="text-gray-800">{label}</div>
            <div className="text-xs text-gray-500">確信度: {Math.round(c.confidence * 100)}%</div>
            <div className="text-xs text-gray-600">理由: {c.reason}</div>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => {
                  const fromId = isCauseOfNew ? c.issue_id : newIssueId;
                  const toId = isCauseOfNew ? newIssueId : c.issue_id;
                  confirmEdge(fromId, toId);
                }}
                style={{ fontSize: 15, height: 44 }}
                className="w-full bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 active:scale-95 transition-all"
              >
                はい、原因として繋げる
              </button>
              <button
                onClick={dismiss}
                style={{ fontSize: 15, height: 44 }}
                className="w-full bg-white border border-gray-300 text-gray-700 rounded-xl font-medium hover:bg-gray-50 active:scale-95 transition-all"
              >
                いいえ、繋げない
              </button>
              <button
                onClick={() => setShowAlternative((v) => !v)}
                style={{ fontSize: 14, height: 40 }}
                className="w-full bg-white border border-gray-300 text-gray-600 rounded-xl hover:bg-gray-50 active:scale-95 transition-all"
              >
                別のノードが原因
              </button>
            </div>

            {showAlternative && (
              <div className="space-y-1 mt-1">
                <div className="text-xs font-medium text-gray-600">原因ノードを選択:</div>
                <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
                  {existingIssues
                    .filter((iss) => iss.id !== newIssueId)
                    .map((iss) => (
                      <button
                        key={iss.id}
                        onClick={() => confirmEdge(iss.id, newIssueId)}
                        style={{ fontSize: 14 }}
                        className="text-left bg-white border border-gray-200 rounded-lg px-3 py-2 hover:bg-blue-50 active:scale-95 transition-all"
                      >
                        {iss.title}
                      </button>
                    ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
