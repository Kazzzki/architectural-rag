'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Search, Loader2, AlertCircle, FileText } from 'lucide-react';

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

export default function IssueMemoSearch({ projectName, onSelectIssue }: IssueMemoSearchProps) {
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

  // 入力 debounce (300ms)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      doSearch(query);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, doSearch]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      doSearch(query);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {/* 検索ボックス */}
      <div className="relative">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
        />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="課題メモを自然言語で検索…（例: 鉄骨納期が遅れた原因）"
          className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white placeholder:text-gray-400"
        />
        {loading && (
          <Loader2
            size={15}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-blue-500 animate-spin"
          />
        )}
      </div>

      {/* エラー表示 */}
      {error && (
        <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* 結果一覧 */}
      {!loading && searched && results.length === 0 && (
        <div className="text-sm text-gray-400 text-center py-6">
          該当するメモが見つかりませんでした
        </div>
      )}

      <div className="flex flex-col gap-2">
        {results.map((r) => (
          <button
            key={r.issue_id}
            onClick={() => onSelectIssue?.(r.issue_id)}
            className="text-left w-full bg-white border border-gray-200 rounded-xl px-4 py-3 hover:border-blue-400 hover:bg-blue-50 transition-colors group"
          >
            {/* タイトル行 */}
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <FileText size={14} className="text-blue-400 flex-shrink-0" />
              <span className="text-sm font-medium text-gray-800 flex-1 min-w-0 truncate">
                {r.title || '（タイトルなし）'}
              </span>
              {r.priority && (
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full flex-shrink-0 ${PRIORITY_BADGE[r.priority] ?? PRIORITY_BADGE.normal}`}
                >
                  {PRIORITY_LABEL[r.priority] ?? r.priority}
                </span>
              )}
            </div>

            {/* メタ情報 */}
            <div className="flex items-center gap-2 mb-1.5 text-[11px] text-gray-500 flex-wrap">
              {r.category && (
                <span className={`font-medium ${CATEGORY_COLOR[r.category] ?? 'text-gray-500'}`}>
                  [{r.category}]
                </span>
              )}
              {r.project_name && !projectName && (
                <span className="truncate">{r.project_name}</span>
              )}
              {r.status && <span className="text-gray-400">{r.status}</span>}
              <span className="ml-auto text-gray-400">
                スコア: {(r.score * 100).toFixed(0)}%
              </span>
            </div>

            {/* スニペット */}
            {r.snippet && (
              <p className="text-xs text-gray-500 leading-relaxed line-clamp-2 group-hover:text-gray-700">
                {r.snippet}
              </p>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
