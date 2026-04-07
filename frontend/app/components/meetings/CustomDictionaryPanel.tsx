'use client';

import { useEffect, useState } from 'react';
import { Book, Plus, Trash2, Loader2 } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface DictEntry {
  id: number;
  project_id: string | null;
  term: string;
  reading: string | null;
  category: string | null;
}

export default function CustomDictionaryPanel() {
  const [entries, setEntries] = useState<DictEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [term, setTerm] = useState('');
  const [reading, setReading] = useState('');
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const fetchEntries = async () => {
    try {
      const res = await authFetch('/api/dictionary');
      if (res.ok) setEntries(await res.json());
    } catch {}
    setLoading(false);
  };

  useEffect(() => { fetchEntries(); }, []);

  const handleAdd = async () => {
    if (!term.trim()) return;
    setAdding(true);
    try {
      const res = await authFetch('/api/dictionary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ term: term.trim(), reading: reading.trim() || null }),
      });
      if (res.ok) {
        setTerm('');
        setReading('');
        setShowForm(false);
        fetchEntries();
      }
    } catch {}
    setAdding(false);
  };

  const handleDelete = async (id: number) => {
    try {
      await authFetch(`/api/dictionary/${id}`, { method: 'DELETE' });
      setEntries(prev => prev.filter(e => e.id !== id));
    } catch {}
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <Book className="w-4 h-4 text-amber-500" />
          カスタム辞書
          <span className="text-xs text-gray-400 font-normal">{entries.length}語</span>
        </h3>
        <button
          onClick={() => setShowForm(!showForm)}
          className="text-xs px-2.5 py-1 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 flex items-center gap-1"
        >
          <Plus className="w-3 h-3" /> 追加
        </button>
      </div>

      {showForm && (
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <input
              type="text"
              value={term}
              onChange={e => setTerm(e.target.value)}
              placeholder="用語 (例: ABC工法)"
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
            />
          </div>
          <div className="flex-1">
            <input
              type="text"
              value={reading}
              onChange={e => setReading(e.target.value)}
              placeholder="読み (任意)"
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
            />
          </div>
          <button
            onClick={handleAdd}
            disabled={adding || !term.trim()}
            className="px-3 py-2 bg-amber-500 text-white text-sm rounded-lg hover:bg-amber-600 disabled:opacity-50"
          >
            {adding ? <Loader2 className="w-4 h-4 animate-spin" /> : '登録'}
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-center py-4">
          <Loader2 className="w-5 h-5 animate-spin text-gray-300 mx-auto" />
        </div>
      ) : entries.length === 0 ? (
        <p className="text-xs text-gray-400 text-center py-3">
          専門用語を登録すると文字起こしの精度が向上します
        </p>
      ) : (
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {entries.map(e => (
            <div key={e.id} className="group flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-50">
              <span className="text-sm text-gray-700 flex-1">{e.term}</span>
              {e.reading && <span className="text-xs text-gray-400">{e.reading}</span>}
              <button
                onClick={() => handleDelete(e.id)}
                className="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-red-500 rounded transition-all"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
