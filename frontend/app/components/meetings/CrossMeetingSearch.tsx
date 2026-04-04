'use client';

import { useState } from 'react';
import { Search, Loader2, MessageSquare, FileText } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface Source {
  id: number;
  title: string;
  date: string;
}

export default function CrossMeetingSearch() {
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setAnswer('');
    setSources([]);
    try {
      const res = await authFetch('/api/meetings/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        setAnswer(data.answer || '');
        setSources(data.sources || []);
      }
    } catch (e) {
      console.error('Cross-meeting search failed:', e);
      setAnswer('検索中にエラーが発生しました。');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 space-y-4">
      <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
        <MessageSquare className="w-4 h-4 text-indigo-500" />
        会議横断検索
      </h3>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="過去の会議について質問... (例: 防水仕様はどう決まった？)"
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="px-4 py-2.5 bg-indigo-600 text-white text-sm rounded-xl hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-1.5 flex-shrink-0"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          検索
        </button>
      </div>

      {answer && (
        <div className="bg-indigo-50 rounded-xl p-4 space-y-3">
          <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{answer}</p>
          {sources.length > 0 && (
            <div className="border-t border-indigo-200 pt-2">
              <p className="text-xs text-indigo-600 font-medium mb-1">参照元:</p>
              <div className="flex flex-wrap gap-2">
                {sources.map(s => (
                  <a
                    key={s.id}
                    href={`/meetings/${s.id}`}
                    className="flex items-center gap-1 px-2 py-1 bg-white rounded-lg text-xs text-indigo-700 hover:bg-indigo-100 transition-colors"
                  >
                    <FileText className="w-3 h-3" />
                    {s.title} ({s.date})
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
