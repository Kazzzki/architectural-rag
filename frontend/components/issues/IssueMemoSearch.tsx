'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Search, Loader2, AlertCircle, FileText, MessageCircle, Send } from 'lucide-react';

interface MemoSearchResult {
  issue_id: string;
  title: string;
  project_name: string;
  category: string;
  priority: string;
  status: string;
  score: number;
  snippet: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: MemoSearchResult[];
}

interface IssueMemoSearchProps {
  /** プロジェクト名を固定してフィルタリングする場合に指定 */
  projectName?: string;
  /** 結果カードをクリックした際のコールバック */
  onSelectIssue?: (issueId: string) => void;
}

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 border border-red-200',
  normal:   'bg-blue-100 text-blue-700 border border-blue-200',
  minor:    'bg-gray-100 text-gray-500 border border-gray-200',
};

const PRIORITY_LABEL: Record<string, string> = {
  critical: '重大',
  normal:   '通常',
  minor:    '軽微',
};

const CATEGORY_COLOR: Record<string, string> = {
  工程: 'text-orange-600',
  コスト: 'text-emerald-600',
  品質: 'text-violet-600',
  安全: 'text-red-600',
};

// ─── 検索タブ ─────────────────────────────────────────
function SearchTab({
  projectName,
  onSelectIssue,
}: {
  projectName?: string;
  onSelectIssue?: (issueId: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MemoSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        setResults([]);
        setSearched(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ q: q.trim(), top_k: '8' });
        if (projectName) params.set('project_name', projectName);
        const res = await authFetch(`/api/issues/memo-search?${params.toString()}`);
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ?? `HTTP ${res.status}`);
        }
        const data: { results: MemoSearchResult[] } = await res.json();
        setResults(data.results);
        setSearched(true);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : '検索に失敗しました');
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [projectName],
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, doSearch]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      doSearch(query);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="課題メモを自然言語で検索…（例: 鉄骨納期が遅れた原因）"
          className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white placeholder:text-gray-400"
        />
        {loading && (
          <Loader2 size={15} className="absolute right-3 top-1/2 -translate-y-1/2 text-blue-500 animate-spin" />
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {!loading && searched && results.length === 0 && (
        <div className="text-sm text-gray-400 text-center py-6">該当するメモが見つかりませんでした</div>
      )}

      <div className="flex flex-col gap-2">
        {results.map((r) => (
          <MemoCard key={r.issue_id} result={r} onSelect={onSelectIssue} showProject={!projectName} />
        ))}
      </div>
    </div>
  );
}

// ─── チャットタブ ──────────────────────────────────────
function ChatTab({ projectName, onSelectIssue }: { projectName?: string; onSelectIssue?: (issueId: string) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend() {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    setError(null);

    const userMsg: ChatMessage = { role: 'user', content: q };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await authFetch('/api/issues/memo-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: q,
          messages: messages.map((m) => ({ role: m.role, content: m.content })),
          project_name: projectName ?? null,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const data: { answer: string; sources: MemoSearchResult[] } = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer, sources: data.sources },
      ]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'エラーが発生しました');
      setMessages((prev) => prev.slice(0, -1)); // ユーザーメッセージを取り消す
      setInput(q);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {/* メッセージ一覧 */}
      <div className="overflow-y-auto flex flex-col gap-3 pb-2 min-h-[260px] max-h-[55vh]">
        {messages.length === 0 && (
          <div className="text-sm text-gray-400 text-center py-8 px-4">
            「あのとき何が原因だったっけ？」など、自然な言葉で質問してください。
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-sm'
                  : 'bg-gray-100 text-gray-800 rounded-bl-sm'
              }`}
            >
              {msg.content}
            </div>
            {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
              <div className="mt-1.5 w-full max-w-[85%] flex flex-col gap-1">
                <span className="text-[10px] text-gray-400 px-1">参照メモ</span>
                {msg.sources.map((s) => (
                  <MemoCard key={s.issue_id} result={s} onSelect={onSelectIssue} showProject={!projectName} compact />
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex items-start">
            <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-2.5 flex items-center gap-2">
              <Loader2 size={14} className="text-blue-500 animate-spin" />
              <span className="text-sm text-gray-500">考えています…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-2">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* 入力エリア */}
      <div className="flex items-end gap-2 pt-2 border-t border-gray-100">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="質問を入力… (Enterで送信、Shift+Enterで改行)"
          rows={2}
          className="flex-1 text-sm border border-gray-300 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none placeholder:text-gray-400"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          className="flex-shrink-0 bg-blue-600 text-white rounded-xl p-2.5 hover:bg-blue-700 disabled:opacity-40 transition-colors"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}

// ─── 共通: メモカード ─────────────────────────────────
function MemoCard({
  result: r,
  onSelect,
  showProject,
  compact = false,
}: {
  result: MemoSearchResult;
  onSelect?: (issueId: string) => void;
  showProject: boolean;
  compact?: boolean;
}) {
  return (
    <button
      onClick={() => onSelect?.(r.issue_id)}
      className="text-left w-full bg-white border border-gray-200 rounded-xl px-4 py-3 hover:border-blue-400 hover:bg-blue-50 transition-colors group"
    >
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <FileText size={14} className="text-blue-400 flex-shrink-0" />
        <span className="text-sm font-medium text-gray-800 flex-1 min-w-0 truncate">
          {r.title || '（タイトルなし）'}
        </span>
        {r.priority && (
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full flex-shrink-0 ${PRIORITY_BADGE[r.priority] ?? PRIORITY_BADGE.normal}`}>
            {PRIORITY_LABEL[r.priority] ?? r.priority}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 mb-1.5 text-[11px] text-gray-500 flex-wrap">
        {r.category && (
          <span className={`font-medium ${CATEGORY_COLOR[r.category] ?? 'text-gray-500'}`}>[{r.category}]</span>
        )}
        {showProject && r.project_name && <span className="truncate">{r.project_name}</span>}
        {r.status && <span className="text-gray-400">{r.status}</span>}
        <span className="ml-auto text-gray-400">スコア: {(r.score * 100).toFixed(0)}%</span>
      </div>
      {!compact && r.snippet && (
        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2 group-hover:text-gray-700">
          {r.snippet}
        </p>
      )}
    </button>
  );
}

// ─── メインコンポーネント ───────────────────────────────
export default function IssueMemoSearch({ projectName, onSelectIssue }: IssueMemoSearchProps) {
  const [activeTab, setActiveTab] = useState<'search' | 'chat'>('search');

  return (
    <div className="flex flex-col gap-3">
      {/* タブ */}
      <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden self-start">
        <button
          onClick={() => setActiveTab('search')}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs transition-colors ${
            activeTab === 'search' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
          }`}
        >
          <Search size={13} />
          検索
        </button>
        <button
          onClick={() => setActiveTab('chat')}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs transition-colors ${
            activeTab === 'chat' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
          }`}
        >
          <MessageCircle size={13} />
          チャット
        </button>
      </div>

      {/* コンテンツ */}
      {activeTab === 'search' ? (
        <SearchTab projectName={projectName} onSelectIssue={onSelectIssue} />
      ) : (
        <ChatTab projectName={projectName} onSelectIssue={onSelectIssue} />
      )}
    </div>
  );
}
