'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, Loader2, Bot, Info } from 'lucide-react';
import { authFetch } from '@/lib/api';
import { Issue } from '@/lib/issue_types';

interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  issuesCount?: number;
  totalIssues?: number;
  strategy?: string;
}

interface Props {
  projectName: string;
  issues: Issue[];
  onHighlightIssue?: (issueId: string) => void;
}

let _id = 0;

const STRATEGY_LABEL: Record<string, string> = {
  sql: 'フィルタ検索',
  semantic: '意味検索',
  aggregate: '集約分析',
  direct: '指定課題',
};

const SUGGESTIONS = [
  '優先度の高い課題を整理して',
  '期限が近い課題は？',
  '未割当の課題を一覧にして',
  '全体の状況をまとめて',
];

export default function IssueAnalysisChat({ projectName, issues, onHighlightIssue }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // テキスト内の課題タイトルをクリッカブルにする
  const renderWithIssueLinks = useCallback((text: string) => {
    if (!onHighlightIssue || issues.length === 0) return text;

    const parts: (string | React.ReactElement)[] = [];
    let remaining = text;
    let key = 0;

    for (const issue of issues) {
      if (!issue.title || issue.title.length < 4) continue;
      const idx = remaining.indexOf(issue.title);
      if (idx === -1) continue;

      if (idx > 0) parts.push(remaining.slice(0, idx));
      parts.push(
        <button
          key={key++}
          onClick={() => onHighlightIssue(issue.id)}
          className="text-indigo-600 hover:text-indigo-800 underline decoration-dotted cursor-pointer"
        >
          {issue.title}
        </button>
      );
      remaining = remaining.slice(idx + issue.title.length);
    }
    if (remaining) parts.push(remaining);
    return parts.length > 1 ? <>{parts}</> : text;
  }, [issues, onHighlightIssue]);

  const handleSend = useCallback(async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || loading) return;
    setInput('');
    setMessages(prev => [...prev, { id: ++_id, role: 'user', content: msg }]);
    setLoading(true);

    try {
      const res = await authFetch('/api/issues/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, project_name: projectName || null }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMessages(prev => [...prev, {
        id: ++_id,
        role: 'assistant',
        content: data.response,
        issuesCount: data.issues_count,
        totalIssues: data.total_issues,
        strategy: data.retrieval_strategy,
      }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        id: ++_id,
        role: 'assistant',
        content: `エラー: ${e instanceof Error ? e.message : '応答を取得できませんでした'}`,
      }]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [input, loading, projectName]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-3 py-2 border-b border-gray-200 bg-gray-50 flex items-center gap-2">
        <Bot className="w-4 h-4 text-indigo-600" />
        <span className="text-xs font-semibold text-gray-600">AI分析</span>
        <span className="text-[10px] text-gray-400 ml-auto">{issues.length}件の課題</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-6 space-y-3">
            <Bot className="w-8 h-8 mx-auto text-gray-300" />
            <p className="text-xs text-gray-400">課題データを分析・整理できます</p>
            <div className="flex flex-col gap-1.5">
              {SUGGESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => handleSend(q)}
                  className="text-[11px] px-3 py-1.5 border border-gray-200 rounded-lg text-gray-600 hover:bg-indigo-50 hover:border-indigo-300 transition-colors text-left"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[90%] rounded-2xl px-3 py-2 text-xs leading-relaxed ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white rounded-tr-sm'
                : 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm shadow-sm'
            }`}>
              <div className="whitespace-pre-wrap">
                {msg.role === 'assistant' ? renderWithIssueLinks(msg.content) : msg.content}
              </div>
              {msg.strategy && (
                <div className="mt-1.5 flex items-center gap-2 text-[10px] opacity-60">
                  <span>{STRATEGY_LABEL[msg.strategy] || msg.strategy}</span>
                  <span>{msg.issuesCount}/{msg.totalIssues}件参照</span>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-3 py-2 shadow-sm">
              <div className="flex gap-1">
                {[0, 150, 300].map(d => (
                  <span key={d} className="w-1.5 h-1.5 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                ))}
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t border-gray-200 bg-white px-2 py-2 flex items-end gap-1.5">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); handleSend(); }
          }}
          placeholder="質問を入力..."
          rows={1}
          disabled={loading}
          className="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2 text-xs bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:bg-white disabled:opacity-50"
          style={{ minHeight: 34, maxHeight: 80 }}
        />
        <button
          onClick={() => handleSend()}
          disabled={loading || !input.trim()}
          className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center hover:bg-indigo-700 disabled:opacity-30 transition-all"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
