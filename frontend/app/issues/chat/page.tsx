'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { authFetch } from '@/lib/api';
import { CaptureResponse } from '@/lib/issue_types';
import { ArrowLeft, ClipboardList, Mic, Send, ChevronDown } from 'lucide-react';
import Link from 'next/link';

// ─── 型定義 ──────────────────────────────────────────────────────────────────

type Msg =
  | { id: number; role: 'user'; text: string }
  | { id: number; role: 'ai'; text: string; draft?: CaptureResponse }
  | { id: number; role: 'system'; text: string };

let _id = 0;
const nextId = () => ++_id;

const PRIORITY_STYLE: Record<string, string> = {
  critical: 'text-red-600 bg-red-50 border-red-200',
  normal:   'text-yellow-700 bg-yellow-50 border-yellow-200',
  minor:    'text-gray-500 bg-gray-50 border-gray-200',
};
const PRIORITY_LABEL: Record<string, string> = {
  critical: '🔴 Critical',
  normal:   '🟡 Normal',
  minor:    '⚪ Minor',
};

// ─── IssueDraftCard ───────────────────────────────────────────────────────────

function IssueDraftCard({ draft }: { draft: CaptureResponse }) {
  const { issue, causal_candidates } = draft;
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());

  async function confirmEdge(fromId: string, toId: string, key: string) {
    try {
      await authFetch('/api/issues/edges/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_id: fromId, to_id: toId, confirmed: true }),
      });
      setConfirmed((prev) => new Set([...prev, key]));
    } catch {
      // noop
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm shadow-sm overflow-hidden text-sm w-full">
      {/* Issue summary */}
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <span className="font-semibold text-gray-800 leading-snug">{issue.title}</span>
          <span
            className={`text-xs px-2 py-0.5 rounded-full border flex-shrink-0 font-medium ${
              PRIORITY_STYLE[issue.priority] ?? PRIORITY_STYLE['normal']
            }`}
          >
            {PRIORITY_LABEL[issue.priority] ?? issue.priority}
          </span>
        </div>
        <div className="flex gap-3 text-xs text-gray-400 mb-2">
          <span>{issue.category}</span>
          <span>·</span>
          <span>{issue.status}</span>
        </div>
        {issue.description && (
          <p className="text-xs text-gray-600 leading-relaxed">{issue.description}</p>
        )}
        {issue.action_next && (
          <div className="mt-2 flex items-start gap-1.5">
            <span className="text-xs text-blue-500 font-medium flex-shrink-0">次のアクション</span>
            <span className="text-xs text-gray-600">{issue.action_next}</span>
          </div>
        )}
      </div>

      {/* Causal candidates */}
      {causal_candidates.length > 0 && (
        <div className="border-t border-amber-100 bg-amber-50 px-4 py-3">
          <p className="text-xs font-semibold text-amber-700 mb-2">因果関係の候補</p>
          <div className="space-y-2">
            {causal_candidates.map((c, i) => {
              const key = `${c.issue_id}-${i}`;
              const fromId = c.direction === 'cause_of_new' ? c.issue_id : issue.id;
              const toId   = c.direction === 'cause_of_new' ? issue.id   : c.issue_id;
              const done   = confirmed.has(key);
              return (
                <div key={i} className="flex items-center justify-between gap-2">
                  <span className="text-xs text-amber-800 flex-1 min-w-0">
                    {c.direction === 'cause_of_new' ? '← ' : '→ '}
                    {c.reason}
                    <span className="text-amber-500 ml-1">({Math.round(c.confidence * 100)}%)</span>
                  </span>
                  {done ? (
                    <span className="text-xs text-green-600 flex-shrink-0 font-medium">✓ 登録</span>
                  ) : (
                    <button
                      onClick={() => confirmEdge(fromId, toId, key)}
                      className="text-xs px-2.5 py-1 rounded-lg border border-amber-300 bg-white text-amber-700 hover:bg-amber-100 flex-shrink-0 transition-colors"
                    >
                      つなぐ
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-gray-100 px-4 py-2 flex items-center justify-between">
        <span className="text-xs text-green-600 font-medium">✓ グラフに登録済み</span>
        <Link
          href="/issues"
          className="text-xs text-blue-500 hover:underline"
        >
          グラフを見る →
        </Link>
      </div>
    </div>
  );
}

// ─── Typing indicator ─────────────────────────────────────────────────────────

function TypingDots() {
  return (
    <div className="flex justify-start gap-2">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center">
        <ClipboardList size={14} className="text-blue-600" />
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center h-4">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── メインページ ─────────────────────────────────────────────────────────────

export default function IssueChatPage() {
  const [projectName, setProjectName] = useState('');
  const [projects, setProjects]       = useState<string[]>([]);
  const [messages, setMessages]       = useState<Msg[]>([
    {
      id: nextId(), role: 'ai',
      text: 'こんにちは！課題を話しかけてください。テキスト入力でも音声入力でもOKです 🎤',
    },
  ]);
  const [input, setInput]           = useState('');
  const [busy, setBusy]             = useState(false);
  const [recording, setRecording]   = useState(false);
  const [transcribing, setTranscribing] = useState(false);

  const mrRef    = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // プロジェクト一覧取得
  useEffect(() => {
    authFetch('/api/issues/projects')
      .then((r) => r.json())
      .then((d) => setProjects(d.projects ?? []))
      .catch(() => {});
  }, []);

  // 自動スクロール
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, busy]);

  // textarea 高さ自動調整
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  // ─── メッセージ送信 ──────────────────────────────────────────────────────

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    if (!projectName.trim()) {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'user', text: trimmed },
        { id: nextId(), role: 'ai', text: 'プロジェクト名を入力してから送信してください 👆' },
      ]);
      setInput('');
      return;
    }

    setMessages((prev) => [...prev, { id: nextId(), role: 'user', text: trimmed }]);
    setInput('');
    setBusy(true);

    try {
      const res = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: trimmed, project_name: projectName }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: CaptureResponse = await res.json();

      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'ai', text: '課題を整理しました ✓', draft: data },
      ]);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'ai', text: `エラー: ${e.message ?? '送信に失敗しました'}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  // ─── 音声録音 ────────────────────────────────────────────────────────────

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        await transcribeAndSend(blob);
      };
      mr.start();
      mrRef.current = mr;
      setRecording(true);
    } catch {
      alert('マイクへのアクセスが許可されていません');
    }
  }, []);

  const stopRecording = useCallback(() => {
    mrRef.current?.stop();
    mrRef.current = null;
    setRecording(false);
  }, []);

  async function transcribeAndSend(blob: Blob) {
    setTranscribing(true);
    try {
      const fd = new FormData();
      fd.append('file', blob, 'voice.webm');
      const res = await authFetch('/api/transcribe', { method: 'POST', body: fd });
      if (res.ok) {
        const data = await res.json();
        const text = (data.text ?? '').trim();
        if (text) await send(text);
      }
    } finally {
      setTranscribing(false);
    }
  }

  const handlePTT = (e: React.TouchEvent | React.MouseEvent, down: boolean) => {
    e.preventDefault();
    if (down) { startRecording(); } else if (recording) { stopRecording(); }
  };

  // ─── レンダリング ────────────────────────────────────────────────────────

  const micLabel = transcribing ? '変換中…' : recording ? '話してください…' : '';

  return (
    <div
      className="flex flex-col bg-gray-50"
      style={{ height: '100dvh', maxWidth: 680, margin: '0 auto' }}
    >
      {/* ヘッダー */}
      <div className="flex items-center gap-2 px-4 py-3 bg-white border-b border-gray-200 flex-shrink-0">
        <Link href="/issues" className="text-gray-400 hover:text-gray-700 flex-shrink-0">
          <ArrowLeft size={18} />
        </Link>
        <ClipboardList size={18} className="text-blue-600 flex-shrink-0" />
        <div className="relative flex-1 min-w-0">
          <input
            list="chat-projects"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="プロジェクトを選択または入力…"
            style={{ fontSize: 14 }}
            className="w-full border border-gray-300 rounded-lg pl-3 pr-8 py-1.5 text-sm bg-white text-gray-800 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
          <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <datalist id="chat-projects">
            {projects.map((p) => <option key={p} value={p} />)}
          </datalist>
        </div>
      </div>

      {/* メッセージ一覧 */}
      <div className="flex-1 overflow-y-auto px-4 py-5 space-y-4">
        {messages.map((msg) => {
          if (msg.role === 'system') {
            return (
              <div key={msg.id} className="text-center text-xs text-gray-400 py-1">
                {msg.text}
              </div>
            );
          }

          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[78%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed shadow-sm">
                  {msg.text}
                </div>
              </div>
            );
          }

          // AI
          return (
            <div key={msg.id} className="flex justify-start gap-2 items-start">
              <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center mt-0.5">
                <ClipboardList size={14} className="text-blue-600" />
              </div>
              <div className="max-w-[85%] space-y-2 min-w-0">
                <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm text-gray-800 shadow-sm leading-relaxed">
                  {msg.text}
                </div>
                {msg.draft && <IssueDraftCard draft={msg.draft} />}
              </div>
            </div>
          );
        })}

        {(busy || transcribing) && <TypingDots />}

        {recording && (
          <div className="flex justify-center">
            <span className="text-xs text-red-500 animate-pulse bg-red-50 px-3 py-1 rounded-full border border-red-200">
              ● 録音中… 離して送信
            </span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 入力エリア */}
      <div
        className="flex-shrink-0 bg-white border-t border-gray-200 px-3 py-3 flex items-end gap-2"
        style={{ paddingBottom: 'calc(12px + env(safe-area-inset-bottom))' }}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder={micLabel || '課題を入力…'}
          disabled={busy || transcribing || recording}
          rows={1}
          style={{ fontSize: 16, minHeight: 40, maxHeight: 120 }}
          className="flex-1 resize-none border border-gray-300 rounded-2xl px-4 py-2 text-sm text-gray-800 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white transition-colors"
        />

        {/* マイクボタン (Push-To-Talk) */}
        <button
          onTouchStart={(e) => handlePTT(e, true)}
          onTouchEnd={(e)   => handlePTT(e, false)}
          onMouseDown={(e)  => handlePTT(e, true)}
          onMouseUp={(e)    => handlePTT(e, false)}
          disabled={busy || transcribing}
          className={`flex-shrink-0 w-11 h-11 rounded-full flex items-center justify-center select-none transition-all
            ${recording
              ? 'bg-red-500 text-white shadow-lg scale-110 animate-pulse'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200 active:scale-95'
            }
            ${(busy || transcribing) ? 'opacity-40 cursor-not-allowed' : ''}
          `}
        >
          <Mic size={18} />
        </button>

        {/* 送信ボタン */}
        <button
          onClick={() => send(input)}
          disabled={!input.trim() || busy || recording}
          className="flex-shrink-0 w-11 h-11 rounded-full bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 disabled:opacity-40 transition-all active:scale-95 shadow-sm"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
