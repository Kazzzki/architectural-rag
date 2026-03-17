'use client';

import React, { useEffect, useRef, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, CausalCandidate, CaptureResponse } from '@/lib/issue_types';
import { Send } from 'lucide-react';

interface IssueChatPanelProps {
  projectName: string;
  issues: Issue[];
  onIssueAdded: (resp: CaptureResponse) => void;
}

type ChatEntry =
  | { id: number; kind: 'user'; text: string }
  | { id: number; kind: 'result'; resp: CaptureResponse }
  | { id: number; kind: 'error'; text: string };

let _uid = 0;
const uid = () => ++_uid;

const PRIORITY_STYLE: Record<string, string> = {
  critical: 'border-red-300 bg-red-50 text-red-700',
  normal:   'border-blue-200 bg-blue-50 text-blue-700',
  minor:    'border-gray-200 bg-gray-50 text-gray-500',
};
const PRIORITY_LABEL: Record<string, string> = {
  critical: '🔴 Critical', normal: '🟡 Normal', minor: '⚪ Minor',
};

// ─── 因果候補の確認カード ────────────────────────────────────────────────────

function CausalCard({
  candidate,
  newIssueId,
  issues,
  onConfirm,
  onDismiss,
}: {
  candidate: CausalCandidate;
  newIssueId: string;
  issues: Issue[];
  onConfirm: (fromId: string, toId: string) => Promise<void>;
  onDismiss: () => void;
}) {
  const [done, setDone] = useState(false);
  const [showAlt, setShowAlt] = useState(false);
  const existingTitle = issues.find((i) => i.id === candidate.issue_id)?.title ?? candidate.issue_id;
  const isCauseOfNew = candidate.direction === 'cause_of_new';
  const label = isCauseOfNew
    ? `「${existingTitle}」が原因の可能性`
    : `「${existingTitle}」に影響する可能性`;

  async function handleConfirm(fromId: string, toId: string) {
    await onConfirm(fromId, toId);
    setDone(true);
  }

  if (done) {
    return (
      <div className="text-xs text-green-600 font-medium py-1">✓ 因果エッジ登録</div>
    );
  }

  return (
    <div className="border border-amber-200 bg-amber-50 rounded-lg p-2.5 space-y-2">
      <div className="text-xs text-amber-800">{label}</div>
      <div className="text-xs text-amber-600">確信度 {Math.round(candidate.confidence * 100)}% · {candidate.reason}</div>
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => {
            const fromId = isCauseOfNew ? candidate.issue_id : newIssueId;
            const toId   = isCauseOfNew ? newIssueId : candidate.issue_id;
            handleConfirm(fromId, toId);
          }}
          className="text-xs px-2.5 py-1 rounded-md bg-green-600 text-white hover:bg-green-700 transition-colors"
        >
          つなぐ
        </button>
        <button
          onClick={onDismiss}
          className="text-xs px-2.5 py-1 rounded-md bg-gray-200 text-gray-600 hover:bg-gray-300 transition-colors"
        >
          スキップ
        </button>
        <button
          onClick={() => setShowAlt((v) => !v)}
          className="text-xs px-2.5 py-1 rounded-md border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
        >
          別のノード
        </button>
      </div>
      {showAlt && (
        <div className="max-h-28 overflow-y-auto flex flex-col gap-1 pt-1">
          {issues
            .filter((iss) => iss.id !== newIssueId)
            .map((iss) => (
              <button
                key={iss.id}
                onClick={() => handleConfirm(iss.id, newIssueId)}
                className="text-xs text-left bg-white border border-gray-200 rounded px-2 py-1 hover:bg-blue-50 hover:border-blue-300 transition-colors"
              >
                {iss.title}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

// ─── キャプチャ結果カード ────────────────────────────────────────────────────

function ResultCard({
  resp,
  issues,
  onEdgeConfirmed,
}: {
  resp: CaptureResponse;
  issues: Issue[];
  onEdgeConfirmed: () => void;
}) {
  const [currentResp, setCurrentResp] = useState(resp);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  // ai_status === 'analyzing' の間、ポーリングで結果を取得
  useEffect(() => {
    if (resp.ai_status !== 'analyzing') return;
    let cancelled = false;
    let attempts = 0;
    const poll = async () => {
      if (cancelled || attempts >= 20) return;
      attempts++;
      try {
        const r = await authFetch(`/api/issues/${resp.issue.id}/analysis`);
        if (r.ok) {
          const d = await r.json();
          if (d.ai_status === 'done' || d.ai_status === 'error') {
            if (!cancelled) {
              setCurrentResp(d);
              if (d.causal_candidates?.length > 0) onEdgeConfirmed();
            }
            return;
          }
        }
      } catch { /* ignore */ }
      if (!cancelled) setTimeout(poll, 600);
    };
    setTimeout(poll, 600);
    return () => { cancelled = true; };
  }, []);

  const { issue, causal_candidates } = currentResp;
  const analyzing = currentResp.ai_status === 'analyzing';
  const prStyle = PRIORITY_STYLE[issue.priority] ?? PRIORITY_STYLE['normal'];

  async function confirmEdge(fromId: string, toId: string) {
    await authFetch('/api/issues/edges/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_id: fromId, to_id: toId, confirmed: true }),
    });
    onEdgeConfirmed();
  }

  const active = causal_candidates.filter((c) => !dismissed.has(c.issue_id));

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden text-xs shadow-sm">
      <div className="px-3 py-2.5 space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold text-gray-800 text-sm leading-tight">{issue.title}</span>
          {analyzing ? (
            <span className="text-xs px-2 py-0.5 rounded-full border font-medium flex-shrink-0 border-amber-200 bg-amber-50 text-amber-600">
              AI分析中…
            </span>
          ) : (
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium flex-shrink-0 ${prStyle}`}>
              {PRIORITY_LABEL[issue.priority] ?? issue.priority}
            </span>
          )}
        </div>
        <div className="flex gap-2 text-gray-400">
          <span>{issue.category}</span><span>·</span><span>{issue.status}</span>
        </div>
        {issue.description && (
          <p className="text-gray-600 leading-relaxed">{issue.description}</p>
        )}
        {issue.action_next && (
          <p className="text-blue-600 font-medium">→ {issue.action_next}</p>
        )}
      </div>

      {active.length > 0 && (
        <div className="px-3 pb-3 space-y-2">
          {active.map((c) => (
            <CausalCard
              key={c.issue_id}
              candidate={c}
              newIssueId={issue.id}
              issues={issues}
              onConfirm={confirmEdge}
              onDismiss={() => setDismissed((prev) => new Set([...prev, c.issue_id]))}
            />
          ))}
        </div>
      )}

      <div className="border-t border-gray-100 px-3 py-1.5">
        <span className="text-green-600 font-medium">✓ グラフに登録</span>
      </div>
    </div>
  );
}

// ─── メインパネル ────────────────────────────────────────────────────────────

export default function IssueChatPanel({ projectName, issues, onIssueAdded }: IssueChatPanelProps) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries, loading]);

  // textarea 高さ自動調整
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 100)}px`;
    }
  }, [text]);

  async function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    if (!projectName) {
      setEntries((prev) => [...prev, { id: uid(), kind: 'error', text: 'プロジェクトを選択してください' }]);
      return;
    }

    setEntries((prev) => [...prev, { id: uid(), kind: 'user', text: trimmed }]);
    setText('');
    setLoading(true);

    try {
      const res = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: trimmed, project_name: projectName }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: CaptureResponse = await res.json();
      onIssueAdded(data);
      setEntries((prev) => [...prev, { id: uid(), kind: 'result', resp: data }]);
    } catch (e: any) {
      setEntries((prev) => [...prev, { id: uid(), kind: 'error', text: e.message ?? '送信エラー' }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ヘッダー */}
      <div className="flex-shrink-0 px-3 py-2 border-b border-gray-200 bg-gray-50">
        <span className="text-xs font-semibold text-gray-500">課題を入力</span>
      </div>

      {/* メッセージ履歴 */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {entries.length === 0 && (
          <p className="text-xs text-gray-400 text-center mt-8 leading-relaxed">
            現場で起きた課題を<br />自由に入力してください
          </p>
        )}

        {entries.map((entry) => {
          if (entry.kind === 'user') {
            return (
              <div key={entry.id} className="flex justify-end">
                <div className="max-w-[85%] bg-blue-600 text-white text-xs rounded-2xl rounded-tr-sm px-3 py-2 leading-relaxed shadow-sm">
                  {entry.text}
                </div>
              </div>
            );
          }
          if (entry.kind === 'error') {
            return (
              <div key={entry.id} className="text-xs text-red-500 text-center py-1">
                {entry.text}
              </div>
            );
          }
          // result
          return (
            <div key={entry.id} className="flex justify-start">
              <div className="w-full">
                <ResultCard
                  resp={entry.resp}
                  issues={issues}
                  onEdgeConfirmed={() => onIssueAdded({ issue: entry.resp.issue, causal_candidates: [], duplicate_candidates: [] })}
                />
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-3 py-2 shadow-sm">
              <div className="flex gap-1 items-center h-4">
                {[0, 150, 300].map((d) => (
                  <span key={d} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                ))}
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 入力エリア */}
      <div className="flex-shrink-0 border-t border-gray-200 bg-white px-2 py-2 flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder="課題を入力… (Enter送信)"
          disabled={loading}
          rows={1}
          style={{ fontSize: 13, minHeight: 36, maxHeight: 100 }}
          className="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2 text-gray-800 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white transition-colors"
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !text.trim()}
          className="flex-shrink-0 w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 disabled:opacity-40 transition-all active:scale-95 shadow-sm"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
