'use client';

import React, { useEffect, useState } from 'react';
import { authFetch, confirmIssueEdge, updateIssue, fetchProjectMembers } from '@/lib/api';
import { CausalCandidate, Issue, CaptureResponse, ProjectMember } from '@/lib/issue_types';
import { CheckCircle, X, FileText, User } from 'lucide-react';

// ---------- Props ----------

interface CausalConfirmCardProps {
  newIssueId: string;
  candidates: CausalCandidate[];
  existingIssues: Issue[];
  variant: 'compact' | 'full' | 'inline';
  /** inline variant: issue object for assignee/memo */
  issue?: Issue;
  /** inline variant: project name for member fetch */
  projectName?: string;
  /** Called when user finishes (all confirmed/dismissed) */
  onDone: () => void;
  /** Called after an edge is confirmed (for graph refresh) */
  onEdgeConfirmed?: () => void;
  /** inline variant: polling for AI analysis */
  aiStatus?: 'analyzing' | 'done' | 'error';
}

// ---------- Shared edge confirm logic ----------

async function doConfirmEdge(fromId: string, toId: string) {
  await confirmIssueEdge(fromId, toId, true);
}

// ---------- Single candidate row ----------

function CandidateRow({
  candidate,
  newIssueId,
  existingIssues,
  variant,
  onConfirmed,
  onDismissed,
}: {
  candidate: CausalCandidate;
  newIssueId: string;
  existingIssues: Issue[];
  variant: 'compact' | 'full' | 'inline';
  onConfirmed: () => void;
  onDismissed: () => void;
}) {
  const [state, setState] = useState<'pending' | 'confirmed' | 'skipped'>('pending');
  const [showAlt, setShowAlt] = useState(false);

  const existingTitle = existingIssues.find((i) => i.id === candidate.issue_id)?.title ?? candidate.issue_id;
  const isCauseOfNew = candidate.direction === 'cause_of_new';
  const defaultFromId = isCauseOfNew ? candidate.issue_id : newIssueId;
  const defaultToId = isCauseOfNew ? newIssueId : candidate.issue_id;

  async function handleConfirm(fromId: string, toId: string) {
    try {
      await doConfirmEdge(fromId, toId);
      setState('confirmed');
      onConfirmed();
    } catch (e) {
      console.error('Edge confirm failed:', e);
    }
  }

  function handleDismiss() {
    setState('skipped');
    onDismissed();
  }

  if (state === 'confirmed') {
    return (
      <div className="flex items-center gap-1.5 py-1">
        <CheckCircle size={14} className="text-green-500" />
        <span className="text-xs text-green-600 font-medium">因果エッジ登録</span>
      </div>
    );
  }

  if (state === 'skipped') {
    return (
      <div className="flex items-center gap-1.5 py-1">
        <X size={14} className="text-gray-400" />
        <span className="text-xs text-gray-400">スキップ</span>
      </div>
    );
  }

  const label = isCauseOfNew
    ? `「${existingTitle}」が原因の可能性`
    : `「${existingTitle}」に影響する可能性`;

  // --- Full variant: large mobile-friendly buttons ---
  if (variant === 'full') {
    return (
      <div className="space-y-2">
        <div style={{ fontSize: 15 }} className="text-gray-800">{label}</div>
        <div className="text-xs text-gray-500">確信度: {Math.round(candidate.confidence * 100)}%</div>
        <div className="text-xs text-gray-600">理由: {candidate.reason}</div>
        <div className="flex flex-col gap-2">
          <button
            onClick={() => handleConfirm(defaultFromId, defaultToId)}
            style={{ fontSize: 15, height: 44 }}
            className="w-full bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 active:scale-95 transition-all"
          >
            はい、原因として繋げる
          </button>
          <button
            onClick={handleDismiss}
            style={{ fontSize: 15, height: 44 }}
            className="w-full bg-white border border-gray-300 text-gray-700 rounded-xl font-medium hover:bg-gray-50 active:scale-95 transition-all"
          >
            いいえ、繋げない
          </button>
          <button
            onClick={() => setShowAlt((v) => !v)}
            style={{ fontSize: 14, height: 40 }}
            className="w-full bg-white border border-gray-300 text-gray-600 rounded-xl hover:bg-gray-50 active:scale-95 transition-all"
          >
            別のノードが原因
          </button>
        </div>
        {showAlt && (
          <AltNodePicker
            existingIssues={existingIssues}
            excludeId={newIssueId}
            onSelect={(id) => handleConfirm(id, newIssueId)}
          />
        )}
      </div>
    );
  }

  // --- Inline variant: row with action buttons ---
  if (variant === 'inline') {
    return (
      <div className="flex items-center gap-2 rounded-lg border bg-white border-gray-200 px-3 py-2">
        <div className="flex-1 min-w-0">
          <span className="text-xs text-gray-500 block">
            {isCauseOfNew ? '← この課題の原因' : '→ この課題の影響先'}
          </span>
          <span className="text-xs font-medium text-gray-800 truncate block">{candidate.reason}</span>
          <span className="text-[10px] text-gray-400">信頼度 {Math.round(candidate.confidence * 100)}%</span>
        </div>
        <div className="flex gap-1 shrink-0">
          <button
            onClick={() => handleConfirm(defaultFromId, defaultToId)}
            className="text-xs px-2 py-1 rounded bg-green-500 text-white hover:bg-green-600 transition-colors"
          >
            繋げる
          </button>
          <button
            onClick={handleDismiss}
            className="text-xs px-2 py-1 rounded bg-gray-200 text-gray-600 hover:bg-gray-300 transition-colors"
          >
            スキップ
          </button>
        </div>
      </div>
    );
  }

  // --- Compact variant: small chat-panel style ---
  return (
    <div className="border border-amber-200 bg-amber-50 rounded-lg p-2.5 space-y-2">
      <div className="text-xs text-amber-800">{label}</div>
      <div className="text-xs text-amber-600">確信度 {Math.round(candidate.confidence * 100)}% · {candidate.reason}</div>
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => handleConfirm(defaultFromId, defaultToId)}
          className="text-xs px-2.5 py-1 rounded-md bg-green-600 text-white hover:bg-green-700 transition-colors"
        >
          つなぐ
        </button>
        <button
          onClick={handleDismiss}
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
        <AltNodePicker
          existingIssues={existingIssues}
          excludeId={newIssueId}
          onSelect={(id) => handleConfirm(id, newIssueId)}
        />
      )}
    </div>
  );
}

// ---------- Alternative node picker ----------

function AltNodePicker({
  existingIssues,
  excludeId,
  onSelect,
}: {
  existingIssues: Issue[];
  excludeId: string;
  onSelect: (issueId: string) => void;
}) {
  return (
    <div className="space-y-1 mt-1">
      <div className="text-xs font-medium text-gray-600">原因ノードを選択:</div>
      <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
        {existingIssues
          .filter((iss) => iss.id !== excludeId)
          .map((iss) => (
            <button
              key={iss.id}
              onClick={() => onSelect(iss.id)}
              className="text-xs text-left bg-white border border-gray-200 rounded-lg px-3 py-2 hover:bg-blue-50 hover:border-blue-300 transition-colors"
            >
              {iss.title}
            </button>
          ))}
      </div>
    </div>
  );
}

// ---------- Inline variant extras (assignee + memo) ----------

function InlineExtras({ issue, projectName }: { issue: Issue; projectName: string }) {
  const [assignee, setAssignee] = useState(issue.assignee || '');
  const [memo, setMemo] = useState(issue.context_memo || '');
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [assigneeSaved, setAssigneeSaved] = useState(false);
  const [memoSaved, setMemoSaved] = useState(false);

  useEffect(() => {
    fetchProjectMembers(projectName).then(setMembers).catch(() => {});
  }, [projectName]);

  async function saveAssignee() {
    if (!assignee.trim()) return;
    await updateIssue(issue.id, { assignee });
    setAssigneeSaved(true);
  }

  async function saveMemo() {
    await updateIssue(issue.id, { context_memo: memo });
    setMemoSaved(true);
  }

  return (
    <div className="space-y-3">
      {/* Assignee */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          <User size={12} className="inline mr-1" />
          担当者
        </label>
        <div className="flex gap-2">
          {members.length > 0 ? (
            <select
              value={assignee}
              onChange={(e) => { setAssignee(e.target.value); setAssigneeSaved(false); }}
              className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-blue-300"
            >
              <option value="">担当者を選択</option>
              {members.map((m) => (
                <option key={m.id} value={m.name}>{m.name}{m.role ? ` (${m.role})` : ''}</option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={assignee}
              onChange={(e) => { setAssignee(e.target.value); setAssigneeSaved(false); }}
              placeholder="担当者名を入力"
              className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-blue-300"
            />
          )}
          <button
            onClick={saveAssignee}
            disabled={!assignee.trim()}
            className="text-xs px-3 py-1.5 rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-40 transition-colors"
          >
            {assigneeSaved ? '✓' : '保存'}
          </button>
        </div>
      </div>
      {/* Memo */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          <FileText size={12} className="inline mr-1" />
          判断メモ
        </label>
        <textarea
          value={memo}
          onChange={(e) => { setMemo(e.target.value); setMemoSaved(false); }}
          placeholder="対応方針や背景など"
          rows={2}
          className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-blue-300 resize-none"
        />
        <div className="flex justify-end mt-1">
          <button
            onClick={saveMemo}
            className="text-xs px-3 py-1 rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-40 transition-colors"
          >
            {memoSaved ? '✓' : 'メモを保存'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- Main component ----------

export default function CausalConfirmCard({
  newIssueId,
  candidates,
  existingIssues,
  variant,
  issue,
  projectName,
  onDone,
  onEdgeConfirmed,
  aiStatus,
}: CausalConfirmCardProps) {
  const [currentCandidates, setCurrentCandidates] = useState(candidates);
  const [processedCount, setProcessedCount] = useState(0);
  const analyzing = aiStatus === 'analyzing';

  // Poll for AI analysis completion
  useEffect(() => {
    if (aiStatus !== 'analyzing') return;
    let cancelled = false;
    let attempts = 0;
    const poll = async () => {
      if (cancelled || attempts >= 20) return;
      attempts++;
      try {
        const r = await authFetch(`/api/issues/${newIssueId}/analysis`);
        if (r.ok) {
          const d = await r.json();
          if (d.ai_status === 'done' || d.ai_status === 'error') {
            if (!cancelled && d.causal_candidates?.length > 0) {
              setCurrentCandidates(d.causal_candidates);
            }
            return;
          }
        }
      } catch { /* ignore */ }
      if (!cancelled) setTimeout(poll, 600);
    };
    setTimeout(poll, 600);
    return () => { cancelled = true; };
  }, [aiStatus, newIssueId]);

  const total = currentCandidates.length;

  function handleProcessed() {
    const next = processedCount + 1;
    setProcessedCount(next);
    onEdgeConfirmed?.();
    if (next >= total) onDone();
  }

  if (total === 0 && !analyzing) {
    if (variant === 'full') return null;
    // compact/inline: show nothing
    return null;
  }

  // --- Full variant wrapper ---
  if (variant === 'full') {
    return (
      <div className="border border-yellow-400 bg-yellow-50 rounded-2xl p-4 space-y-3">
        <div className="text-sm font-semibold text-yellow-800">
          {analyzing ? 'AI分析中…' : 'AIが因果関係の候補を検出しました'}
        </div>
        {currentCandidates.map((c) => (
          <CandidateRow
            key={c.issue_id}
            candidate={c}
            newIssueId={newIssueId}
            existingIssues={existingIssues}
            variant="full"
            onConfirmed={handleProcessed}
            onDismissed={handleProcessed}
          />
        ))}
      </div>
    );
  }

  // --- Inline variant wrapper ---
  if (variant === 'inline') {
    return (
      <div className="space-y-3">
        {currentCandidates.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-600 mb-2">関連する既存課題（因果候補）</p>
            <div className="space-y-2">
              {currentCandidates.map((c) => (
                <CandidateRow
                  key={c.issue_id}
                  candidate={c}
                  newIssueId={newIssueId}
                  existingIssues={existingIssues}
                  variant="inline"
                  onConfirmed={() => onEdgeConfirmed?.()}
                  onDismissed={() => {}}
                />
              ))}
            </div>
          </div>
        )}
        {currentCandidates.length === 0 && !analyzing && (
          <p className="text-xs text-gray-500">関連する既存課題は見つかりませんでした。</p>
        )}
        {issue && projectName && (
          <InlineExtras issue={issue} projectName={projectName} />
        )}
      </div>
    );
  }

  // --- Compact variant wrapper (for chat panel) ---
  return (
    <div className="space-y-2">
      {analyzing && (
        <div className="text-xs text-amber-600 font-medium">AI分析中…</div>
      )}
      {currentCandidates.map((c) => (
        <CandidateRow
          key={c.issue_id}
          candidate={c}
          newIssueId={newIssueId}
          existingIssues={existingIssues}
          variant="compact"
          onConfirmed={handleProcessed}
          onDismissed={handleProcessed}
        />
      ))}
    </div>
  );
}
