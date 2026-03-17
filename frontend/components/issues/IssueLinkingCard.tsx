'use client';

import React, { useState } from 'react';
import { ExternalLink, User, FileText, Link, X, CheckCircle } from 'lucide-react';
import { IssueCaptureData, CausalCandidate, Issue, ProjectMember } from '../../lib/issue_types';
import { confirmIssueEdge, updateIssue } from '../../lib/api';

interface Props {
  data: IssueCaptureData;
  members: ProjectMember[];
  projectName: string;
}

const CATEGORY_COLORS: Record<string, string> = {
  '工程': 'bg-blue-100 text-blue-700',
  'コスト': 'bg-yellow-100 text-yellow-700',
  '品質': 'bg-green-100 text-green-700',
  '安全': 'bg-red-100 text-red-700',
};

const PRIORITY_COLORS: Record<string, string> = {
  'critical': 'bg-red-100 text-red-700',
  'normal': 'bg-orange-100 text-orange-700',
  'minor': 'bg-gray-100 text-gray-600',
};

const PRIORITY_LABELS: Record<string, string> = {
  'critical': '重大',
  'normal': '通常',
  'minor': '軽微',
};

export default function IssueLinkingCard({ data, members, projectName }: Props) {
  const { issue, causal_candidates, duplicate_candidates } = data;

  const [edgeStates, setEdgeStates] = useState<Record<string, 'pending' | 'confirmed' | 'skipped'>>(
    () => Object.fromEntries(causal_candidates.map(c => [c.issue_id, 'pending']))
  );
  const [assignee, setAssignee] = useState<string>(issue.assignee || '');
  const [assigneeSaved, setAssigneeSaved] = useState(false);
  const [memo, setMemo] = useState<string>(issue.context_memo || '');
  const [memoSaved, setMemoSaved] = useState(false);
  const [savingAssignee, setSavingAssignee] = useState(false);
  const [savingMemo, setSavingMemo] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  const handleEdge = async (candidate: CausalCandidate, connect: boolean) => {
    const fromId = candidate.direction === 'cause_of_new' ? candidate.issue_id : issue.id;
    const toId = candidate.direction === 'cause_of_new' ? issue.id : candidate.issue_id;
    try {
      await confirmIssueEdge(fromId, toId, connect);
      setEdgeStates(prev => ({ ...prev, [candidate.issue_id]: connect ? 'confirmed' : 'skipped' }));
    } catch (e) {
      console.error('Edge confirm failed:', e);
    }
  };

  const handleAssigneeSave = async () => {
    if (!assignee.trim()) return;
    setSavingAssignee(true);
    try {
      await updateIssue(issue.id, { assignee });
      setAssigneeSaved(true);
    } catch (e) {
      console.error('Assignee save failed:', e);
    } finally {
      setSavingAssignee(false);
    }
  };

  const handleMemoSave = async () => {
    setSavingMemo(true);
    try {
      await updateIssue(issue.id, { context_memo: memo });
      setMemoSaved(true);
    } catch (e) {
      console.error('Memo save failed:', e);
    } finally {
      setSavingMemo(false);
    }
  };

  return (
    <div className="mt-3 rounded-xl border border-orange-200 bg-orange-50 text-sm overflow-hidden">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-4 py-2 bg-orange-100 border-b border-orange-200">
        <div className="flex items-center gap-2 font-semibold text-orange-800">
          <FileText size={14} />
          課題を登録しました
        </div>
        <button
          onClick={() => setCollapsed(v => !v)}
          className="text-orange-500 hover:text-orange-700 transition-colors"
          title={collapsed ? '展開' : '折りたたむ'}
        >
          {collapsed ? '▼' : '▲'}
        </button>
      </div>

      {!collapsed && (
        <div className="px-4 py-3 space-y-4">
          {/* 課題概要 */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-800">{issue.title}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${CATEGORY_COLORS[issue.category] || 'bg-gray-100 text-gray-600'}`}>
              {issue.category}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${PRIORITY_COLORS[issue.priority] || 'bg-gray-100 text-gray-600'}`}>
              {PRIORITY_LABELS[issue.priority] || issue.priority}
            </span>
          </div>
          {issue.description && (
            <p className="text-xs text-gray-600">{issue.description}</p>
          )}

          {/* 重複候補警告 */}
          {duplicate_candidates.length > 0 && (
            <div className="rounded-lg bg-yellow-50 border border-yellow-200 px-3 py-2 text-xs text-yellow-800">
              ⚠️ 類似課題が{duplicate_candidates.length}件あります。グラフで確認してください。
            </div>
          )}

          {/* 担当者設定 */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              <User size={12} className="inline mr-1" />
              担当者
            </label>
            <div className="flex gap-2">
              {members.length > 0 ? (
                <select
                  value={assignee}
                  onChange={e => { setAssignee(e.target.value); setAssigneeSaved(false); }}
                  className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-orange-300"
                >
                  <option value="">担当者を選択</option>
                  {members.map(m => (
                    <option key={m.id} value={m.name}>{m.name}{m.role ? ` (${m.role})` : ''}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={assignee}
                  onChange={e => { setAssignee(e.target.value); setAssigneeSaved(false); }}
                  placeholder="担当者名を入力"
                  className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-orange-300"
                />
              )}
              <button
                onClick={handleAssigneeSave}
                disabled={savingAssignee || !assignee.trim()}
                className="text-xs px-3 py-1.5 rounded-lg bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {assigneeSaved ? '✓ 保存済み' : savingAssignee ? '保存中…' : '保存'}
              </button>
            </div>
          </div>

          {/* 判断メモ */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              <FileText size={12} className="inline mr-1" />
              判断メモ（なぜこの課題が重要か・対応方針など）
            </label>
            <textarea
              value={memo}
              onChange={e => { setMemo(e.target.value); setMemoSaved(false); }}
              placeholder="例: A工事の遅延が直接の原因。追加工程費の承認が必要。"
              rows={2}
              className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-orange-300 resize-none"
            />
            <div className="flex justify-end mt-1">
              <button
                onClick={handleMemoSave}
                disabled={savingMemo}
                className="text-xs px-3 py-1 rounded-lg bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {memoSaved ? '✓ 保存済み' : savingMemo ? '保存中…' : 'メモを保存'}
              </button>
            </div>
          </div>

          {/* 因果候補 */}
          {causal_candidates.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-gray-600 mb-2">
                <Link size={12} className="inline mr-1" />
                関連する既存課題（因果候補）
              </p>
              <div className="space-y-2">
                {causal_candidates.map(c => {
                  const state = edgeStates[c.issue_id];
                  return (
                    <div
                      key={c.issue_id}
                      className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${
                        state === 'confirmed' ? 'bg-green-50 border-green-200' :
                        state === 'skipped' ? 'bg-gray-50 border-gray-200 opacity-60' :
                        'bg-white border-gray-200'
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <span className="text-xs text-gray-500 block">
                          {c.direction === 'cause_of_new' ? '← この課題の原因' : '→ この課題の影響先'}
                        </span>
                        <span className="text-xs font-medium text-gray-800 truncate block">
                          {c.reason}
                        </span>
                        <span className="text-[10px] text-gray-400">
                          信頼度 {Math.round(c.confidence * 100)}%
                        </span>
                      </div>
                      {state === 'pending' ? (
                        <div className="flex gap-1 shrink-0">
                          <button
                            onClick={() => handleEdge(c, true)}
                            className="text-xs px-2 py-1 rounded bg-green-500 text-white hover:bg-green-600 transition-colors"
                          >
                            繋げる
                          </button>
                          <button
                            onClick={() => handleEdge(c, false)}
                            className="text-xs px-2 py-1 rounded bg-gray-200 text-gray-600 hover:bg-gray-300 transition-colors"
                          >
                            スキップ
                          </button>
                        </div>
                      ) : state === 'confirmed' ? (
                        <CheckCircle size={16} className="text-green-500 shrink-0" />
                      ) : (
                        <X size={16} className="text-gray-400 shrink-0" />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <p className="text-xs text-gray-500">関連する既存課題は見つかりませんでした。</p>
          )}

          {/* グラフへのリンク */}
          <div className="flex justify-end">
            <a
              href={`/issues?project=${encodeURIComponent(projectName)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-orange-600 hover:text-orange-800 transition-colors"
            >
              <ExternalLink size={12} />
              グラフで確認
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
