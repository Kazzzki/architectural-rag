'use client';

import React, { useEffect, useRef, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, CausalCandidate, CaptureResponse } from '@/lib/issue_types';
import { Send, Camera, X, Sparkles } from 'lucide-react';

interface IssueChatPanelProps {
  projectName: string;
  issues: Issue[];
  onIssueAdded: (resp: CaptureResponse) => void;
}

type ChatEntry =
  | { id: number; kind: 'user'; text: string }
  | { id: number; kind: 'user-photo'; previewUrl: string; text: string }
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

// --- Pattern Suggest ---
interface PatternResult { id: string; similarity: number; titles: string; categories: string; node_count: number; }

function PatternSuggest({ issueTitle, issueDescription }: { issueTitle: string; issueDescription: string }) {
  const [patterns, setPatterns] = React.useState<PatternResult[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [dismissed, setDismissed] = React.useState(false);
  const searched = React.useRef(false);

  React.useEffect(() => {
    if (searched.current || !issueTitle) return;
    searched.current = true;
    setLoading(true);
    authFetch('/api/issues/patterns/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `${issueTitle} ${issueDescription}`.trim() }),
    }).then(r => r.json())
      .then(d => setPatterns((d.patterns || []).filter((p: PatternResult) => p.similarity >= 0.5)))
      .catch(() => {}).finally(() => setLoading(false));
  }, [issueTitle, issueDescription]);

  if (dismissed || (!loading && patterns.length === 0)) return null;

  return (
    <div className="border-t border-amber-100 bg-amber-50/50 px-3 py-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-medium text-amber-700 flex items-center gap-1"><Sparkles size={10} /> 類似パターン</span>
        <button onClick={() => setDismissed(true)} className="text-[10px] text-gray-400"><X size={10} /></button>
      </div>
      {loading ? <div className="text-[10px] text-amber-600 animate-pulse">検索中...</div> : (
        <div className="space-y-1">
          {patterns.map(p => (
            <div key={p.id} className="text-[10px] text-amber-800 bg-amber-100/60 rounded px-2 py-1.5">
              <div className="font-medium">{p.titles}</div>
              <div className="text-amber-600 mt-0.5">{p.categories} · {p.node_count}ノード · 類似度 {Math.round(p.similarity * 100)}%</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

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
      <PatternSuggest issueTitle={issue.title} issueDescription={issue.description || ''} />
    </div>
  );
}

// ─── メインパネル ────────────────────────────────────────────────────────────

export default function IssueChatPanel({ projectName, issues, onIssueAdded }: IssueChatPanelProps) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  function handlePhotoSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoFile(file);
    const url = URL.createObjectURL(file);
    setPhotoPreview(url);
    // reset input so same file can be re-selected
    e.target.value = '';
  }

  function clearPhoto() {
    setPhotoFile(null);
    if (photoPreview) {
      URL.revokeObjectURL(photoPreview);
      setPhotoPreview(null);
    }
  }

  async function handleSubmit() {
    if (loading) return;
    if (!projectName) {
      setEntries((prev) => [...prev, { id: uid(), kind: 'error', text: 'プロジェクトを選択してください' }]);
      return;
    }

    // 写真送信モード
    if (photoFile) {
      const preview = photoPreview!;
      setEntries((prev) => [...prev, { id: uid(), kind: 'user-photo', previewUrl: preview, text: '写真から課題を抽出中…' }]);
      clearPhoto();
      setLoading(true);
      try {
        const form = new FormData();
        form.append('image', photoFile);
        form.append('project_name', projectName);
        const res = await authFetch('/api/issues/capture-photo', { method: 'POST', body: form });
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(errBody.detail || `写真解析エラー (${res.status})`);
        }
        const data: CaptureResponse & { extracted_text?: string } = await res.json();
        onIssueAdded(data);
        setEntries((prev) => [...prev, { id: uid(), kind: 'result', resp: data }]);
      } catch (e: any) {
        setEntries((prev) => [...prev, { id: uid(), kind: 'error', text: e.message ?? '写真解析エラー。ネットワーク接続を確認してください。' }]);
      } finally {
        setLoading(false);
      }
      return;
    }

    // テキスト送信モード
    const trimmed = text.trim();
    if (!trimmed) return;

    setEntries((prev) => [...prev, { id: uid(), kind: 'user', text: trimmed }]);
    setText('');
    setLoading(true);

    try {
      const res = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: trimmed, project_name: projectName }),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({ detail: res.statusText }));
        const detail = errBody.detail || res.statusText;
        const msg = res.status >= 500
          ? `サーバーエラー: ${detail}。しばらく待ってから再試行してください。`
          : res.status === 422
          ? `入力を解析できませんでした: ${detail}`
          : `エラー (${res.status}): ${detail}`;
        throw new Error(msg);
      }
      const data: CaptureResponse = await res.json();
      onIssueAdded(data);
      setEntries((prev) => [...prev, { id: uid(), kind: 'result', resp: data }]);
    } catch (e: any) {
      setEntries((prev) => [...prev, { id: uid(), kind: 'error', text: e.message ?? '送信エラー。ネットワーク接続を確認してください。' }]);
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
          if (entry.kind === 'user-photo') {
            return (
              <div key={entry.id} className="flex justify-end">
                <div className="max-w-[85%] space-y-1">
                  <img src={entry.previewUrl} alt="送信した写真" className="rounded-xl max-h-40 object-cover border border-blue-200 shadow-sm" />
                  <div className="text-[10px] text-gray-400 text-right">{entry.text}</div>
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

      {/* 写真プレビュー */}
      {photoPreview && (
        <div className="flex-shrink-0 px-3 pt-2 flex items-start gap-2">
          <div className="relative inline-block">
            <img src={photoPreview} alt="選択中の写真" className="h-20 rounded-lg object-cover border border-gray-200 shadow-sm" />
            <button
              onClick={clearPhoto}
              className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-gray-700 text-white flex items-center justify-center hover:bg-gray-900"
            >
              <X size={10} />
            </button>
          </div>
          <p className="text-[11px] text-gray-500 mt-1 leading-relaxed">この写真を送信すると<br />Gemini Vision で課題を抽出します</p>
        </div>
      )}

      {/* 入力エリア */}
      <div className="flex-shrink-0 border-t border-gray-200 bg-white px-2 py-2 flex items-end gap-2">
        {/* 写真アップロードボタン */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={handlePhotoSelect}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={loading}
          title="写真から課題を抽出"
          className="flex-shrink-0 w-9 h-9 rounded-full border border-gray-300 text-gray-500 flex items-center justify-center hover:bg-gray-100 disabled:opacity-40 transition-all active:scale-95"
        >
          <Camera size={15} />
        </button>
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
          placeholder={photoFile ? '（写真を選択中）送信ボタンで解析' : '課題を入力… (Enter送信)'}
          disabled={loading || !!photoFile}
          rows={1}
          style={{ fontSize: 13, minHeight: 36, maxHeight: 100 }}
          className="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2 text-gray-800 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white transition-colors disabled:opacity-60"
        />
        <button
          onClick={handleSubmit}
          disabled={loading || (!text.trim() && !photoFile)}
          className="flex-shrink-0 w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 disabled:opacity-40 transition-all active:scale-95 shadow-sm"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
