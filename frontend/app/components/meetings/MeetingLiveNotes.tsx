'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Pencil, Trash2, X, Check, MessageSquare, CheckCircle2, Target, AlertTriangle } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface LiveNote {
  id: number;
  session_id: number;
  timestamp_sec: number;
  content: string;
  note_type: string;
  created_at: string;
}

interface Props {
  sessionId: number;
  elapsedSec: number;
  /** 新しいノートが追加されたとき */
  onNoteAdded?: () => void;
}

const NOTE_TYPE_CONFIG: Record<string, { icon: typeof MessageSquare; label: string; color: string; bgColor: string }> = {
  memo: { icon: MessageSquare, label: 'メモ', color: 'text-gray-600', bgColor: 'bg-gray-100' },
  decision: { icon: CheckCircle2, label: '決定', color: 'text-green-600', bgColor: 'bg-green-100' },
  action: { icon: Target, label: 'アクション', color: 'text-blue-600', bgColor: 'bg-blue-100' },
  risk: { icon: AlertTriangle, label: 'リスク', color: 'text-amber-600', bgColor: 'bg-amber-100' },
};

function formatTimestamp(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function parsePrefix(input: string): { noteType: string; content: string } {
  if (input.startsWith('/d ')) return { noteType: 'decision', content: input.slice(3) };
  if (input.startsWith('/a ')) return { noteType: 'action', content: input.slice(3) };
  if (input.startsWith('/r ')) return { noteType: 'risk', content: input.slice(3) };
  return { noteType: 'memo', content: input };
}

export default function MeetingLiveNotes({ sessionId, elapsedSec, onNoteAdded }: Props) {
  const [notes, setNotes] = useState<LiveNote[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');
  const [userScrolled, setUserScrolled] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 初回読み込み
  useEffect(() => {
    authFetch(`/api/meetings/${sessionId}/live-notes`)
      .then(res => res.ok ? res.json() : [])
      .then(setNotes)
      .catch(() => {});
  }, [sessionId]);

  // 自動スクロール（ユーザーが手動スクロール中は停止）
  useEffect(() => {
    if (!userScrolled && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [notes, userScrolled]);

  const handleScroll = useCallback(() => {
    if (!listRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = listRef.current;
    setUserScrolled(scrollHeight - scrollTop - clientHeight > 40);
  }, []);

  const handleSubmit = async () => {
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    const { noteType, content } = parsePrefix(trimmed);
    if (!content.trim()) return;

    setSending(true);
    try {
      const res = await authFetch('/api/meetings/live-notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          timestamp_sec: elapsedSec,
          content: content.trim(),
          note_type: noteType,
        }),
      });
      if (res.ok) {
        const note = await res.json();
        setNotes(prev => [...prev, note]);
        setInput('');
        setUserScrolled(false);
        onNoteAdded?.();
      }
    } catch (e) {
      console.error('Failed to create live note:', e);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleEdit = async (noteId: number) => {
    if (!editContent.trim()) return;
    try {
      const res = await authFetch(`/api/meetings/live-notes/${noteId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent.trim() }),
      });
      if (res.ok) {
        const updated = await res.json();
        setNotes(prev => prev.map(n => n.id === noteId ? updated : n));
        setEditingId(null);
      }
    } catch (e) {
      console.error('Failed to update note:', e);
    }
  };

  const handleDelete = async (noteId: number) => {
    try {
      const res = await authFetch(`/api/meetings/live-notes/${noteId}`, { method: 'DELETE' });
      if (res.ok) {
        setNotes(prev => prev.filter(n => n.id !== noteId));
      }
    } catch (e) {
      console.error('Failed to delete note:', e);
    }
  };

  // プレフィックスに応じた表示色を入力中にプレビュー
  const currentType = parsePrefix(input).noteType;
  const currentConfig = NOTE_TYPE_CONFIG[currentType] || NOTE_TYPE_CONFIG.memo;

  return (
    <div className="bg-white rounded-2xl border border-gray-200 flex flex-col">
      {/* Sticky入力エリア（常に上部に表示） */}
      <div className="sticky top-0 z-10 bg-white border-b border-gray-100 p-4 rounded-t-2xl">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${currentConfig.bgColor} ${currentConfig.color}`}>
            {currentConfig.label}
          </span>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="メモを入力... [Enter送信]"
            disabled={sending}
            className="flex-1 px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-transparent disabled:opacity-50"
          />
        </div>
        <p className="text-xs text-gray-400 mt-1.5 ml-1">
          /d=決定 /a=アクション /r=リスク
        </p>
      </div>

      {/* メモ履歴 */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto max-h-64 p-4 space-y-2"
      >
        {notes.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-sm text-gray-400">
              メモを入力するとタイムスタンプ付きで記録されます
            </p>
          </div>
        ) : (
          notes.map(note => {
            const config = NOTE_TYPE_CONFIG[note.note_type] || NOTE_TYPE_CONFIG.memo;
            const Icon = config.icon;
            const isEditing = editingId === note.id;

            return (
              <div
                key={note.id}
                className="group flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 transition-colors animate-in slide-in-from-bottom-1"
              >
                <span className="text-xs font-mono text-blue-500 mt-0.5 flex-shrink-0 w-14 text-right">
                  {formatTimestamp(note.timestamp_sec)}
                </span>
                <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${config.color}`} />
                <div className="flex-1 min-w-0">
                  {isEditing ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="text"
                        value={editContent}
                        onChange={e => setEditContent(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') handleEdit(note.id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        autoFocus
                        className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-300"
                      />
                      <button onClick={() => handleEdit(note.id)} className="p-1 text-green-600 hover:bg-green-50 rounded">
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => setEditingId(null)} className="p-1 text-gray-400 hover:bg-gray-100 rounded">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-700">{note.content}</p>
                  )}
                </div>
                {!isEditing && (
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    <button
                      onClick={() => { setEditingId(note.id); setEditContent(note.content); }}
                      className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => handleDelete(note.id)}
                      className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
