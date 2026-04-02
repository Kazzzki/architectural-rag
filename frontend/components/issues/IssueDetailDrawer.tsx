'use client';

import React, { useCallback, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import { authFetch, fetchProjectMembers } from '@/lib/api';
import { Issue, ProjectMember, IssueAttachment, CausalSuggestion } from '@/lib/issue_types';
import { X, Trash2, Eye, Pencil, Plus, StickyNote, Loader2, Paperclip, Upload, Sparkles, Check, XCircle, Edit3 } from 'lucide-react';
import ConfirmDialog from './ConfirmDialog';

// --- Note Section ---
interface Note { id: string; content: string; author: string | null; created_at: string; }

function NoteSection({ issueId }: { issueId: string }) {
  const [notes, setNotes] = React.useState<Note[]>([]);
  const [newNote, setNewNote] = React.useState('');
  const [adding, setAdding] = React.useState(false);
  const [expanded, setExpanded] = React.useState(true);

  React.useEffect(() => {
    authFetch(`/api/issues/${issueId}/notes`).then(r => r.json())
      .then(d => setNotes(d.notes || [])).catch(() => {});
  }, [issueId]);

  const handleAdd = async () => {
    if (!newNote.trim() || adding) return;
    setAdding(true);
    try {
      const res = await authFetch(`/api/issues/${issueId}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newNote.trim() }),
      });
      if (res.ok) {
        const note = await res.json();
        setNotes(prev => [note, ...prev]);
        setNewNote('');
      }
    } finally { setAdding(false); }
  };

  const handleDelete = async (noteId: string) => {
    await authFetch(`/api/issues/notes/${noteId}`, { method: 'DELETE' });
    setNotes(prev => prev.filter(n => n.id !== noteId));
  };

  return (
    <div>
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-500 mb-2"
      >
        <StickyNote size={12} />
        ノート ({notes.length})
        <span className="text-[10px]">{expanded ? '▼' : '▶'}</span>
      </button>

      {expanded && (
        <div className="space-y-2">
          {/* Add note */}
          <div className="flex gap-1.5">
            <input
              type="text"
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); }}
              placeholder="ノートを追加..."
              className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <button
              onClick={handleAdd}
              disabled={!newNote.trim() || adding}
              className="px-2 py-1.5 bg-blue-600 text-white rounded-lg text-xs disabled:opacity-30"
            >
              {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            </button>
          </div>

          {/* Note list */}
          {notes.map(note => (
            <div key={note.id} className="flex items-start gap-2 py-1.5 px-2 bg-yellow-50 border border-yellow-200 rounded-lg group">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-gray-700 whitespace-pre-wrap">{note.content}</p>
                <p className="text-[10px] text-gray-400 mt-0.5">
                  {new Date(note.created_at).toLocaleDateString('ja-JP', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
              <button
                onClick={() => handleDelete(note.id)}
                className="text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 p-1"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Attachment Section ---
const MAX_VISIBLE_THUMBS = 3;

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
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('attachment_type', file.type.startsWith('image/') ? 'photo' : 'report');
      const res = await authFetch(`/api/issues/${issueId}/attachments`, {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const att = await res.json();
        setAttachments(prev => [att, ...prev]);
      } else {
        const errData = await res.json().catch(() => ({ detail: 'アップロード失敗' }));
        setError(errData.detail || 'アップロード失敗');
      }
    } catch {
      setError('ネットワークエラー');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (attId: string) => {
    await authFetch(`/api/issues/attachments/${attId}`, { method: 'DELETE' });
    setAttachments(prev => prev.filter(a => a.id !== attId));
  };

  const visibleAtts = attachments.slice(0, MAX_VISIBLE_THUMBS);
  const overflowCount = attachments.length - MAX_VISIBLE_THUMBS;

  return (
    <div>
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-500 mb-2"
      >
        <Paperclip size={12} />
        添付 ({attachments.length})
        <span className="text-[10px]">{expanded ? '▼' : '▶'}</span>
      </button>

      {expanded && (
        <div className="space-y-2">
          {/* Upload button */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,application/pdf"
            onChange={handleUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="w-full text-xs border border-dashed border-gray-300 rounded-lg py-3 hover:bg-gray-50 text-gray-400 flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
          >
            {uploading ? (
              <><Loader2 size={12} className="animate-spin" /> アップロード中...</>
            ) : (
              <><Upload size={12} /> 写真や図面をタップして追加</>
            )}
          </button>

          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center justify-between">
              <span>{error}</span>
              <button onClick={() => { setError(null); fileInputRef.current?.click(); }} className="text-red-600 underline ml-2">再試行</button>
            </div>
          )}

          {/* Thumbnail grid */}
          {visibleAtts.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {visibleAtts.map(att => (
                <div key={att.id} className="relative group rounded-lg overflow-hidden border border-gray-200 bg-gray-50">
                  {att.thumbnail_path ? (
                    <img
                      src={`/api/issues/attachments/${att.id}/thumbnail`}
                      alt={att.caption || '添付画像'}
                      className="w-full h-20 object-cover cursor-pointer"
                      onClick={() => window.open(`/api/issues/attachments/${att.id}/file`, '_blank')}
                    />
                  ) : (
                    <div
                      className="w-full h-20 flex items-center justify-center text-gray-400 cursor-pointer text-xs"
                      onClick={() => window.open(`/api/issues/attachments/${att.id}/file`, '_blank')}
                    >
                      📄 PDF
                    </div>
                  )}
                  <button
                    onClick={() => handleDelete(att.id)}
                    className="absolute top-1 right-1 bg-black/50 text-white rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {overflowCount > 0 && (
            <p className="text-[10px] text-gray-400 text-center">+{overflowCount} 件</p>
          )}

          {attachments.length === 0 && !uploading && (
            <p className="text-[10px] text-gray-300 text-center py-1">添付ファイルなし</p>
          )}
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
    setLoading(true);
    setError(null);
    setSuggestions([]);
    setAcceptedIds(new Set());
    try {
      const res = await authFetch(`/api/issues/${issueId}/suggest-causes`, { method: 'POST' });
      const data = await res.json();
      if (data.ai_status === 'error') {
        setError(data.error || 'AI分析が一時的に利用できません');
      }
      setSuggestions(data.suggestions || []);
    } catch {
      setError('ネットワークエラー');
    } finally {
      setLoading(false);
    }
  }, [issueId]);

  const handleAccept = async (idx: number, title: string, description: string) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      // 1. 新ノードを作成
      const captureRes = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_input: `${title}: ${description}`,
          project_name: projectName || '',
          skip_ai: true,
        }),
      });
      if (!captureRes.ok) throw new Error('ノード作成失敗');
      const captureData = await captureRes.json();
      const newIssueId = captureData.issue?.id;

      if (newIssueId) {
        // 2. エッジ作成 (新ノード → 対象課題)
        await authFetch('/api/issues/edges/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ from_id: newIssueId, to_id: issueId, confirmed: true }),
        });
      }

      setAcceptedIds(prev => new Set([...prev, idx]));
      setEditingIdx(null);
      onCauseAccepted?.();
    } catch (e) {
      setError('原因ノードの作成に失敗しました');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-1.5 text-xs font-medium text-gray-500"
        >
          <Sparkles size={12} />
          AI原因分析
          <span className="text-[10px]">{expanded ? '▼' : '▶'}</span>
        </button>
        {expanded && !loading && (
          <button
            onClick={fetchSuggestions}
            className="text-[10px] text-blue-500 hover:text-blue-700"
          >
            {suggestions.length > 0 ? '再分析' : '分析開始'}
          </button>
        )}
      </div>

      {expanded && (
        <div className="space-y-2">
          {/* Loading shimmer */}
          {loading && (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="animate-pulse bg-gray-100 rounded-lg h-16 border border-gray-200" />
              ))}
              <p className="text-[10px] text-gray-400 text-center">Gemini で分析中...</p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              <p>{error}</p>
              <button onClick={fetchSuggestions} className="text-red-600 underline mt-1 text-[10px]">再試行</button>
            </div>
          )}

          {/* Suggestions */}
          {!loading && suggestions.map((s, idx) => (
            <div
              key={idx}
              className={`border rounded-lg p-3 transition-colors ${
                acceptedIds.has(idx)
                  ? 'bg-green-50 border-green-200'
                  : 'bg-white border-gray-200 hover:border-blue-300'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-800">{s.title}</p>
                  <p className="text-[10px] text-gray-500 mt-0.5">{s.description}</p>
                  <p className="text-[10px] text-gray-400 mt-1">理由: {s.reason}</p>
                </div>
                {/* Confidence bar */}
                <div className="flex-shrink-0 w-10 text-center">
                  <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                    <div
                      className={`h-1.5 rounded-full ${s.confidence >= 0.7 ? 'bg-green-500' : s.confidence >= 0.5 ? 'bg-yellow-500' : 'bg-gray-400'}`}
                      style={{ width: `${s.confidence * 100}%` }}
                    />
                  </div>
                  <span className="text-[9px] text-gray-400">{Math.round(s.confidence * 100)}%</span>
                </div>
              </div>

              {/* Edit mode */}
              {editingIdx === idx && (
                <div className="mt-2 space-y-1.5">
                  <input
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                    placeholder="タイトル"
                  />
                  <input
                    value={editDesc}
                    onChange={e => setEditDesc(e.target.value)}
                    className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                    placeholder="説明"
                  />
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => handleAccept(idx, editTitle, editDesc)}
                      disabled={submitting || !editTitle.trim()}
                      className="flex-1 text-[10px] bg-blue-600 text-white rounded py-1 disabled:opacity-50"
                    >
                      {submitting ? '作成中...' : '採用'}
                    </button>
                    <button
                      onClick={() => setEditingIdx(null)}
                      className="text-[10px] text-gray-500 px-2"
                    >
                      キャンセル
                    </button>
                  </div>
                </div>
              )}

              {/* Action buttons */}
              {!acceptedIds.has(idx) && editingIdx !== idx && (
                <div className="flex gap-1.5 mt-2">
                  <button
                    onClick={() => handleAccept(idx, s.title, s.description)}
                    disabled={submitting}
                    className="flex items-center gap-1 text-[10px] bg-blue-600 text-white rounded px-2 py-1 hover:bg-blue-700 disabled:opacity-50"
                  >
                    <Check size={10} /> 採用
                  </button>
                  <button
                    onClick={() => { setEditingIdx(idx); setEditTitle(s.title); setEditDesc(s.description); }}
                    className="flex items-center gap-1 text-[10px] border border-gray-200 rounded px-2 py-1 hover:bg-gray-50 text-gray-600"
                  >
                    <Edit3 size={10} /> 編集して採用
                  </button>
                  <button
                    onClick={() => setSuggestions(prev => prev.filter((_, i) => i !== idx))}
                    className="flex items-center gap-1 text-[10px] text-gray-400 px-2 py-1 hover:text-red-500"
                  >
                    <XCircle size={10} />
                  </button>
                </div>
              )}

              {acceptedIds.has(idx) && (
                <p className="text-[10px] text-green-600 mt-1 flex items-center gap-1">
                  <Check size={10} /> 原因ノードを作成しました
                </p>
              )}
            </div>
          ))}

          {/* Empty state */}
          {!loading && !error && suggestions.length === 0 && (
            <div className="text-center py-4">
              <button
                onClick={fetchSuggestions}
                className="text-xs bg-blue-50 text-blue-600 border border-blue-200 rounded-lg px-4 py-2 hover:bg-blue-100 flex items-center gap-1.5 mx-auto"
              >
                <Sparkles size={12} /> AI原因分析を実行
              </button>
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
  issues?: Issue[];
  onClose: () => void;
  onUpdated: (updated: Issue) => void;
  onDeleted?: (issueId: string) => void;
  onSelectIssue?: (issue: Issue) => void;
}

const PRIORITY_OPTIONS = ['critical', 'normal', 'minor'] as const;
const STATUS_OPTIONS = ['発生中', '対応中', '解決済み'] as const;
const CATEGORY_OPTIONS = ['工程', 'コスト', '品質', '安全'] as const;

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

export default function IssueDetailDrawer({ issue, issues, onClose, onUpdated, onDeleted, onSelectIssue }: IssueDetailDrawerProps) {
  const [title, setTitle] = useState('');
  const [editingTitle, setEditingTitle] = useState(false);
  const [priority, setPriority] = useState<string>('normal');
  const [status, setStatus] = useState<string>('発生中');
  const [category, setCategory] = useState<string>('工程');
  const [actionNext, setActionNext] = useState('');
  const [description, setDescription] = useState('');
  const [cause, setCause] = useState('');
  const [impact, setImpact] = useState('');
  const [assignee, setAssignee] = useState('');
  const [deadline, setDeadline] = useState('');
  const [memo, setMemo] = useState('');
  const [memoPreview, setMemoPreview] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [projectOptions, setProjectOptions] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    if (issue) {
      setTitle(issue.title);
      setPriority(issue.priority);
      setStatus(issue.status);
      setCategory(issue.category);
      setActionNext(issue.action_next ?? '');
      setDescription(issue.description ?? '');
      setCause(issue.cause ?? '');
      setImpact(issue.impact ?? '');
      setAssignee(issue.assignee ?? '');
      setDeadline(issue.deadline ?? '');
      setMemo(issue.context_memo ?? '');
      setProjectName(issue.project_name ?? '');
      setEditingTitle(false);
      // Fetch members for assignee suggestions
      fetchProjectMembers(issue.project_name).then(setMembers).catch(() => {});
      // Fetch available projects
      authFetch('/api/issues/projects-summary').then(r => r.json()).then(d => {
        const names = (d.projects || []).map((p: { project_name: string }) => p.project_name);
        setProjectOptions(names);
      }).catch(() => {});
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

  async function handleDelete() {
    if (!issue) return;
    try {
      await authFetch(`/api/issues/${issue.id}`, { method: 'DELETE' });
      onDeleted?.(issue.id);
      onClose();
    } catch (e) {
      console.error('delete failed', e);
    } finally {
      setShowDeleteConfirm(false);
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

      <div
        className={[
          'fixed z-50 flex flex-col bg-white shadow-2xl',
          'bottom-0 left-0 right-0 max-h-[78vh] rounded-t-2xl border-t border-gray-200',
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
            {/* Editable title */}
            {editingTitle ? (
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onBlur={() => { setEditingTitle(false); if (title !== issue.title) patch({ title }); }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { setEditingTitle(false); if (title !== issue.title) patch({ title }); }
                  if (e.key === 'Escape') { setTitle(issue.title); setEditingTitle(false); }
                }}
                autoFocus
                className="font-semibold text-sm text-gray-800 leading-tight w-full border border-blue-400 rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            ) : (
              <div
                onClick={() => setEditingTitle(true)}
                className="font-semibold text-sm text-gray-800 leading-tight cursor-text hover:bg-gray-50 rounded px-1 py-0.5 -mx-1"
                title="クリックして編集"
              >
                {issue.title}
              </div>
            )}
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${PRIORITY_BADGE[priority] ?? PRIORITY_BADGE.normal}`}>
                {priority === 'critical' ? 'Critical' : priority === 'normal' ? 'Normal' : 'Minor'}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[status] ?? ''}`}>
                {status}
              </span>
              <span className="text-xs text-gray-400">{category}</span>
              {issue.project_name && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 border border-indigo-200 font-medium">
                  {issue.project_name}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 flex-shrink-0 p-2.5 -mr-1 rounded-lg hover:bg-gray-100 transition-colors"
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
              onChange={(e) => { setPriority(e.target.value); patch({ priority: e.target.value }); }}
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
              onChange={(e) => { setStatus(e.target.value); patch({ status: e.target.value }); }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          {/* カテゴリ */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">カテゴリ</label>
            <select
              value={category}
              onChange={(e) => { setCategory(e.target.value); patch({ category: e.target.value }); }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {CATEGORY_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* プロジェクト */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">プロジェクト</label>
            <div className="flex gap-2">
              <select
                value={projectName}
                onChange={(e) => { setProjectName(e.target.value); patch({ project_name: e.target.value }); }}
                className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                {!projectOptions.includes(projectName) && projectName && (
                  <option value={projectName}>{projectName}</option>
                )}
                {projectOptions.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
          </div>

          {/* 担当者 */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">担当者</label>
            {members.length > 0 ? (
              <select
                value={assignee}
                onChange={(e) => { setAssignee(e.target.value); patch({ assignee: e.target.value }); }}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                <option value="">未割り当て</option>
                {members.map((m) => (
                  <option key={m.id} value={m.name}>{m.name}{m.role ? ` (${m.role})` : ''}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
                onBlur={() => patch({ assignee })}
                placeholder="担当者名"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            )}
          </div>

          {/* 期限 */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">期限</label>
            <input
              type="date"
              value={deadline}
              onChange={(e) => { setDeadline(e.target.value); patch({ deadline: e.target.value || null }); }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
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

          {/* 推定原因 */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">推定原因</label>
            <textarea
              value={cause}
              onChange={(e) => setCause(e.target.value)}
              onBlur={() => patch({ cause })}
              rows={2}
              placeholder="未入力"
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            />
          </div>

          {/* 影響 */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">影響</label>
            <textarea
              value={impact}
              onChange={(e) => setImpact(e.target.value)}
              onBlur={() => patch({ impact })}
              rows={2}
              placeholder="未入力"
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

          {/* メモ (Markdown対応) */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium text-gray-500">メモ</label>
              <button
                onClick={() => { if (memoPreview) { /* switching to edit */ } else { patch({ context_memo: memo }); } setMemoPreview(v => !v); }}
                className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600"
              >
                {memoPreview ? <><Pencil size={10} /> 編集</> : <><Eye size={10} /> プレビュー</>}
              </button>
            </div>
            {memoPreview ? (
              <div className="prose prose-sm max-w-none text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white min-h-[100px] overflow-y-auto max-h-[200px]">
                {memo ? (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeSanitize]}
                    components={{
                      a: ({ href, children, ...props }) => (
                        <a {...props} href={href} className="text-indigo-600 hover:text-indigo-800 underline" target="_blank" rel="noopener noreferrer">{children}</a>
                      ),
                    }}
                  >
                    {memo.replace(/\[\[([^\]]+)\]\]/g, (_, title) => {
                      const linked = issues?.find((i: Issue) => i.title === title);
                      return linked ? `[${title}](#issue-${linked.id})` : `**⟦${title}⟧**`;
                    })}
                  </ReactMarkdown>
                ) : (
                  <p className="text-gray-400 italic">メモを追加... (#タグ や [[課題名]] が使えます)</p>
                )}
              </div>
            ) : (
              <textarea
                value={memo}
                onChange={(e) => setMemo(e.target.value)}
                onBlur={() => patch({ context_memo: memo })}
                rows={4}
                placeholder="#タグ [[課題名リンク]] Markdown対応"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white font-mono"
              />
            )}
          </div>

          {/* タグ表示 */}
          {memo && (
            <div className="flex flex-wrap gap-1">
              {(memo.match(/#[\w\u3040-\u9faf]+/g) || []).map((tag: string, i: number) => (
                <span key={i} className="text-[10px] px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full">
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* AI原因分析 */}
          {issue && <AISuggestSection issueId={issue.id} projectName={issue.project_name} onCauseAccepted={() => onUpdated(issue)} />}

          {/* 添付ファイル */}
          {issue && <AttachmentSection issueId={issue.id} />}

          {/* ノート一覧 */}
          {issue && <NoteSection issueId={issue.id} />}
        </div>

        {/* フッター */}
        <div className="p-4 border-t border-gray-100 flex-shrink-0 pb-safe space-y-2">
          <button
            onClick={toggleCollapse}
            disabled={saving}
            className="w-full text-sm border border-gray-200 rounded-xl py-2.5 hover:bg-gray-50 text-gray-600 font-medium transition-colors disabled:opacity-50"
          >
            {issue.is_collapsed === 1 ? '子ノードを展開する' : '子ノードを折りたたむ'}
          </button>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="w-full text-sm border border-red-200 rounded-xl py-2.5 hover:bg-red-50 text-red-600 font-medium transition-colors flex items-center justify-center gap-1.5"
          >
            <Trash2 size={14} />
            課題を削除
          </button>
        </div>
      </div>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={showDeleteConfirm}
        title="課題を削除"
        message={`「${issue.title}」を削除しますか？関連する因果エッジも全て削除されます。`}
        confirmLabel="削除"
        danger
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}
