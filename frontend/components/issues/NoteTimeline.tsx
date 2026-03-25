'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { IssueNote } from '@/lib/issue_types';
import { Send, Trash2, Edit2, Check, X } from 'lucide-react';

interface NoteTimelineProps {
  issueId: string;
}

export default function NoteTimeline({ issueId }: NoteTimelineProps) {
  const [notes, setNotes] = useState<IssueNote[]>([]);
  const [newContent, setNewContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');

  useEffect(() => {
    fetchNotes();
  }, [issueId]);

  async function fetchNotes() {
    try {
      const res = await authFetch(`/api/issues/${issueId}/notes`);
      if (res.ok) {
        const data = await res.json();
        setNotes(data.notes || []);
      }
    } catch {}
  }

  async function handleCreate() {
    if (!newContent.trim()) return;
    setLoading(true);
    try {
      const res = await authFetch(`/api/issues/${issueId}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newContent.trim() }),
      });
      if (res.ok) {
        const note = await res.json();
        setNotes((prev) => [...prev, note]);
        setNewContent('');
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleUpdate(noteId: string) {
    if (!editContent.trim()) return;
    try {
      const res = await authFetch(`/api/issues/notes/${noteId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent.trim() }),
      });
      if (res.ok) {
        const updated = await res.json();
        setNotes((prev) => prev.map((n) => (n.id === noteId ? updated : n)));
        setEditingId(null);
      }
    } catch {}
  }

  async function handleDelete(noteId: string) {
    try {
      const res = await authFetch(`/api/issues/notes/${noteId}`, { method: 'DELETE' });
      if (res.ok) {
        setNotes((prev) => prev.filter((n) => n.id !== noteId));
      }
    } catch {}
  }

  function formatTime(iso: string) {
    try {
      const d = new Date(iso);
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch {
      return iso;
    }
  }

  return (
    <div>
      <label className="text-xs font-medium text-gray-500 block mb-2">タイムライン</label>

      {/* メモ一覧 */}
      {notes.length === 0 && (
        <div className="text-xs text-gray-400 py-3 text-center">メモはまだありません</div>
      )}

      <div className="space-y-2 mb-3 max-h-[200px] overflow-y-auto">
        {notes.map((note) => (
          <div key={note.id} className="flex gap-2 group">
            {/* タイムライン線 */}
            <div className="flex flex-col items-center flex-shrink-0">
              <div className="w-2 h-2 rounded-full bg-blue-400 mt-1.5" />
              <div className="w-px flex-1 bg-gray-200" />
            </div>

            <div className="flex-1 min-w-0 pb-2">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-[10px] text-gray-400">{formatTime(note.created_at)}</span>
                {note.author && <span className="text-[10px] text-gray-500 font-medium">{note.author}</span>}
                <div className="ml-auto flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => { setEditingId(note.id); setEditContent(note.content); }}
                    className="p-0.5 text-gray-400 hover:text-gray-600"
                  >
                    <Edit2 size={11} />
                  </button>
                  <button
                    onClick={() => handleDelete(note.id)}
                    className="p-0.5 text-gray-400 hover:text-red-500"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>

              {editingId === note.id ? (
                <div className="flex gap-1">
                  <input
                    type="text"
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleUpdate(note.id); if (e.key === 'Escape') setEditingId(null); }}
                    className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                    autoFocus
                  />
                  <button onClick={() => handleUpdate(note.id)} className="text-green-600 p-0.5"><Check size={14} /></button>
                  <button onClick={() => setEditingId(null)} className="text-gray-400 p-0.5"><X size={14} /></button>
                </div>
              ) : (
                <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">{note.content}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 新規メモ入力 */}
      <div className="flex gap-1.5">
        <input
          type="text"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); }}
          placeholder="メモを追加..."
          className="flex-1 text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
          disabled={loading}
        />
        <button
          onClick={handleCreate}
          disabled={loading || !newContent.trim()}
          className="text-blue-600 hover:text-blue-700 disabled:text-gray-300 p-1"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
