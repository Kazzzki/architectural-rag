'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, IssueAttachment, CausalSuggestion } from '@/lib/issue_types';
import { X, Paperclip, Upload, Loader2, Sparkles, Check, Edit3, XCircle } from 'lucide-react';
import NoteTimeline from './NoteTimeline';
import AIInvestigatePanel from './AIInvestigatePanel';

// --- Attachment Section ---
function AttachmentSection({ issueId }: { issueId: string }) {
  const [attachments, setAttachments] = React.useState<IssueAttachment[]>([]);
  const [uploading, setUploading] = React.useState(false);
  const [expanded, setExpanded] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    authFetch(`/api/issues/${issueId}/attachments`).then(r => r.json())
      .then(d => setAttachments(d.attachments || [])).catch(() => {});
  }, [issueId]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || uploading) return;
    setUploading(true); setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('attachment_type', file.type.startsWith('image/') ? 'photo' : 'report');
      const res = await authFetch(`/api/issues/${issueId}/attachments`, { method: 'POST', body: formData });
      if (res.ok) { const att = await res.json(); setAttachments(prev => [att, ...prev]); }
      else { const err = await res.json().catch(() => ({ detail: 'アップロード失敗' })); setError(err.detail); }
    } catch { setError('ネットワークエラー'); }
    finally { setUploading(false); if (fileInputRef.current) fileInputRef.current.value = ''; }
  };

  const handleDelete = async (attId: string) => {
    await authFetch(`/api/issues/attachments/${attId}`, { method: 'DELETE' });
    setAttachments(prev => prev.filter(a => a.id !== attId));
  };

  return (
    <div>
      <button onClick={() => setExpanded(v => !v)} className="flex items-center gap-1.5 text-xs font-medium text-gray-500 mb-2">
        <Paperclip size={12} /> 添付 ({attachments.length}) <span className="text-[10px]">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <div className="space-y-2">
          <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={handleUpload} className="hidden" />
          <button onClick={() => fileInputRef.current?.click()} disabled={uploading}
            className="w-full text-xs border border-dashed border-gray-300 rounded-lg py-3 hover:bg-gray-50 text-gray-400 flex items-center justify-center gap-1.5 disabled:opacity-50">
            {uploading ? <><Loader2 size={12} className="animate-spin" /> アップロード中...</> : <><Upload size={12} /> 写真や図面をタップして追加</>}
          </button>
          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center justify-between">
              <span>{error}</span>
              <button onClick={() => { setError(null); fileInputRef.current?.click(); }} className="text-red-600 underline ml-2">再試行</button>
            </div>
          )}
          {attachments.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {attachments.slice(0, 3).map(att => (
                <div key={att.id} className="relative group rounded-lg overflow-hidden border border-gray-200 bg-gray-50">
                  {att.thumbnail_path ? (
                    <img src={`/api/issues/attachments/${att.id}/thumbnail`} alt={att.caption || ''} className="w-full h-20 object-cover cursor-pointer"
                      onClick={() => window.open(`/api/issues/attachments/${att.id}/file`, '_blank')} />
                  ) : (
                    <div className="w-full h-20 flex items-center justify-center text-gray-400 cursor-pointer text-xs"
                      onClick={() => window.open(`/api/issues/attachments/${att.id}/file`, '_blank')}>📄 PDF</div>
                  )}
                  <button onClick={() => handleDelete(att.id)}
                    className="absolute top-1 right-1 bg-black/50 text-white rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}
          {attachments.length > 3 && <p className="text-[10px] text-gray-400 text-center">+{attachments.length - 3} 件</p>}
        </div>
      )}
    </div>
  );
}

// --- AI Cause Suggestion Section ---
function AISuggestSection({ issueId, projectName, onCauseAccepted }: { issueId: string; projectName?: string; onCauseAccepted?: () => void }) {
  const [suggestions, setSuggestions] = React.useState<CausalSuggestion[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [expanded, setExpanded] = React.useState(true);
  const [acceptedIds, setAcceptedIds] = React.useState<Set<number>>(new Set());
  const [editingIdx, setEditingIdx] = React.useState<number | null>(null);
  const [editTitle, setEditTitle] = React.useState('');
  const [editDesc, setEditDesc] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);

  const fetchSuggestions = React.useCallback(async () => {
    setLoading(true); setError(null); setSuggestions([]); setAcceptedIds(new Set());
    try {
      const res = await authFetch(`/api/issues/${issueId}/suggest-causes`, { method: 'POST' });
      const data = await res.json();
      if (data.ai_status === 'error') setError(data.error || 'AI分析が一時的に利用できません');
      setSuggestions(data.suggestions || []);
    } catch { setError('ネットワークエラー'); }
    finally { setLoading(false); }
  }, [issueId]);

  const handleAccept = async (idx: number, title: string, description: string) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const captureRes = await authFetch('/api/issues/capture', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: `${title}: ${description}`, project_name: projectName || '', skip_ai: true }),
      });
      if (!captureRes.ok) throw new Error('failed');
      const captureData = await captureRes.json();
      const newId = captureData.issue?.id;
      if (newId) {
        await authFetch('/api/issues/edges/confirm', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ from_id: newId, to_id: issueId, confirmed: true }),
        });
      }
      setAcceptedIds(prev => new Set([...prev, idx]));
      setEditingIdx(null);
      onCauseAccepted?.();
    } catch { setError('原因ノードの作成に失敗しました'); }
    finally { setSubmitting(false); }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <button onClick={() => setExpanded(v => !v)} className="flex items-center gap-1.5 text-xs font-medium text-gray-500">
          <Sparkles size={12} /> AI原因分析 <span className="text-[10px]">{expanded ? '▼' : '▶'}</span>
        </button>
        {expanded && !loading && (
          <button onClick={fetchSuggestions} className="text-[10px] text-blue-500 hover:text-blue-700">
            {suggestions.length > 0 ? '再分析' : '分析開始'}
          </button>
        )}
      </div>
      {expanded && (
        <div className="space-y-2">
          {loading && (
            <div className="space-y-2">
              {[1, 2, 3].map(i => <div key={i} className="animate-pulse bg-gray-100 rounded-lg h-16 border border-gray-200" />)}
              <p className="text-[10px] text-gray-400 text-center">Gemini で分析中...</p>
            </div>
          )}
          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              <p>{error}</p>
              <button onClick={fetchSuggestions} className="text-red-600 underline mt-1 text-[10px]">再試行</button>
            </div>
          )}
          {!loading && suggestions.map((s, idx) => (
            <div key={idx} className={`border rounded-lg p-3 transition-colors ${acceptedIds.has(idx) ? 'bg-green-50 border-green-200' : 'bg-white border-gray-200 hover:border-blue-300'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-800">{s.title}</p>
                  <p className="text-[10px] text-gray-500 mt-0.5">{s.description}</p>
                  <p className="text-[10px] text-gray-400 mt-1">理由: {s.reason}</p>
                </div>
                <div className="flex-shrink-0 w-10 text-center">
                  <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                    <div className={`h-1.5 rounded-full ${s.confidence >= 0.7 ? 'bg-green-500' : s.confidence >= 0.5 ? 'bg-yellow-500' : 'bg-gray-400'}`}
                      style={{ width: `${s.confidence * 100}%` }} />
                  </div>
                  <span className="text-[9px] text-gray-400">{Math.round(s.confidence * 100)}%</span>
                </div>
              </div>
              {editingIdx === idx && (
                <div className="mt-2 space-y-1.5">
                  <input value={editTitle} onChange={e => setEditTitle(e.target.value)} className="w-full text-xs border border-gray-200 rounded px-2 py-1" placeholder="タイトル" />
                  <input value={editDesc} onChange={e => setEditDesc(e.target.value)} className="w-full text-xs border border-gray-200 rounded px-2 py-1" placeholder="説明" />
                  <div className="flex gap-1.5">
                    <button onClick={() => handleAccept(idx, editTitle, editDesc)} disabled={submitting || !editTitle.trim()} className="flex-1 text-[10px] bg-blue-600 text-white rounded py-1 disabled:opacity-50">{submitting ? '作成中...' : '採用'}</button>
                    <button onClick={() => setEditingIdx(null)} className="text-[10px] text-gray-500 px-2">キャンセル</button>
                  </div>
                </div>
              )}
              {!acceptedIds.has(idx) && editingIdx !== idx && (
                <div className="flex gap-1.5 mt-2">
                  <button onClick={() => handleAccept(idx, s.title, s.description)} disabled={submitting} className="flex items-center gap-1 text-[10px] bg-blue-600 text-white rounded px-2 py-1 hover:bg-blue-700 disabled:opacity-50"><Check size={10} /> 採用</button>
                  <button onClick={() => { setEditingIdx(idx); setEditTitle(s.title); setEditDesc(s.description); }} className="flex items-center gap-1 text-[10px] border border-gray-200 rounded px-2 py-1 hover:bg-gray-50 text-gray-600"><Edit3 size={10} /> 編集</button>
                  <button onClick={() => setSuggestions(prev => prev.filter((_, i) => i !== idx))} className="text-[10px] text-gray-400 px-1 hover:text-red-500"><XCircle size={10} /></button>
                </div>
              )}
              {acceptedIds.has(idx) && <p className="text-[10px] text-green-600 mt-1 flex items-center gap-1"><Check size={10} /> 原因ノードを作成しました</p>}
            </div>
          ))}
          {!loading && !error && suggestions.length === 0 && (
            <div className="text-center py-4">
              <button onClick={fetchSuggestions} className="text-xs bg-blue-50 text-blue-600 border border-blue-200 rounded-lg px-4 py-2 hover:bg-blue-100 flex items-center gap-1.5 mx-auto"><Sparkles size={12} /> AI原因分析を実行</button>
              <p className="text-[10px] text-gray-300 mt-2">Geminiが考えられる原因を提案します</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface IssueDetailDrawerProps {
  issue: Issue | null;
  onClose: () => void;
  onUpdated: (updated: Issue) => void;
}

const PRIORITY_OPTIONS = ['critical', 'normal', 'minor'] as const;
const STATUS_OPTIONS = ['発生中', '対応中', '解決済み'] as const;

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  normal:   'bg-blue-100 text-blue-700 border-blue-200',
  minor:    'bg-gray-100 text-gray-500 border-gray-200',
};

const STATUS_BADGE: Record<string, string> = {
  '発生中': 'bg-red-100 text-red-600',
  '対応中': 'bg-orange-100 text-orange-600',
  '解決済み': 'bg-green-100 text-green-600',
};

export default function IssueDetailDrawer({ issue, onClose, onUpdated }: IssueDetailDrawerProps) {
  const [priority, setPriority] = useState<string>('normal');
  const [status, setStatus] = useState<string>('発生中');
  const [actionNext, setActionNext] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (issue) {
      setPriority(issue.priority);
      setStatus(issue.status);
      setActionNext(issue.action_next ?? '');
      setDescription(issue.description ?? '');
    }
  }, [issue]);

  async function patch(body: object) {
    if (!issue) return;
    setSaving(true);
    try {
      const res = await authFetch(`/api/issues/${issue.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const updated: Issue = await res.json();
        onUpdated(updated);
      }
    } finally {
      setSaving(false);
    }
  }

  async function toggleCollapse() {
    if (!issue) return;
    await patch({ is_collapsed: issue.is_collapsed === 1 ? 0 : 1 });
  }

  if (!issue) return null;

  return (
    <>
      {/* オーバーレイ (モバイルのみ) */}
      <div
        className="fixed inset-0 bg-black/30 z-40 md:hidden"
        onClick={onClose}
      />

      {/* ドロワー本体
          モバイル: 下からスライドするボトムシート
          デスクトップ: 右からスライドするサイドパネル */}
      <div
        className={[
          'fixed z-50 flex flex-col bg-white shadow-2xl',
          // モバイル: ボトムシート
          'bottom-0 left-0 right-0 max-h-[78vh] rounded-t-2xl border-t border-gray-200',
          // デスクトップ: サイドパネル
          'md:bottom-auto md:left-auto md:right-0 md:top-0 md:max-h-none md:h-full md:w-80 md:rounded-none md:border-t-0 md:border-l md:border-gray-200',
        ].join(' ')}
        style={{ transition: 'transform 0.25s ease-out' }}
      >
        {/* ドラッグハンドル (モバイルのみ) */}
        <div className="md:hidden flex justify-center pt-3 pb-1 flex-shrink-0">
          <div className="w-10 h-1 bg-gray-300 rounded-full" />
        </div>

        {/* ヘッダー */}
        <div className="flex items-start justify-between px-4 py-3 border-b border-gray-100 flex-shrink-0">
          <div className="flex-1 min-w-0 pr-2">
            <div className="font-semibold text-sm text-gray-800 leading-tight">{issue.title}</div>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${PRIORITY_BADGE[priority] ?? PRIORITY_BADGE.normal}`}>
                {priority === 'critical' ? 'Critical' : priority === 'normal' ? 'Normal' : 'Minor'}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[status] ?? ''}`}>
                {status}
              </span>
              <span className="text-xs text-gray-400">{issue.category}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 flex-shrink-0 p-1 -mr-1 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* 重要度 */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">重要度</label>
            <select
              value={priority}
              onChange={(e) => {
                setPriority(e.target.value);
                patch({ priority: e.target.value });
              }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {PRIORITY_OPTIONS.map((p) => (
                <option key={p} value={p}>{p === 'critical' ? 'Critical' : p === 'normal' ? 'Normal' : 'Minor'}</option>
              ))}
            </select>
          </div>

          {/* ステータス */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">ステータス</label>
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                patch({ status: e.target.value });
              }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          {/* 詳細説明 */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">詳細説明</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => patch({ description })}
              rows={3}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            />
          </div>

          {/* 次のアクション */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">次のアクション</label>
            <textarea
              value={actionNext}
              onChange={(e) => setActionNext(e.target.value)}
              onBlur={() => patch({ action_next: actionNext })}
              rows={3}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            />
          </div>

          {/* 推定原因 */}
          {issue.cause && (
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">推定原因</label>
              <div className="text-sm text-gray-700 bg-gray-50 rounded-lg p-3 leading-relaxed">{issue.cause}</div>
            </div>
          )}

          {/* 影響 */}
          {issue.impact && (
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">影響</label>
              <div className="text-sm text-gray-700 bg-gray-50 rounded-lg p-3 leading-relaxed">{issue.impact}</div>
            </div>
          )}

          {/* AI原因分析 */}
          <AISuggestSection issueId={issue.id} projectName={issue.project_name} onCauseAccepted={() => onUpdated(issue)} />

          {/* 添付ファイル */}
          <AttachmentSection issueId={issue.id} />

          {/* タイムラインメモ */}
          <NoteTimeline issueId={issue.id} />

          {/* AI調査 */}
          <AIInvestigatePanel issue={issue} />
        </div>

        {/* フッター: 折りたたみトグル */}
        <div className="p-4 border-t border-gray-100 flex-shrink-0 pb-safe">
          <button
            onClick={toggleCollapse}
            disabled={saving}
            className="w-full text-sm border border-gray-200 rounded-xl py-2.5 hover:bg-gray-50 text-gray-600 font-medium transition-colors disabled:opacity-50"
          >
            {issue.is_collapsed === 1 ? '子ノードを展開する' : '子ノードを折りたたむ'}
          </button>
        </div>
      </div>
    </>
  );
}
