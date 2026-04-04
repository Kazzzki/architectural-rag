'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Mic,
  Square,
  ChevronRight,
  ChevronDown,
  FileText,
  Clock,
  Users,
  FolderOpen,
  Loader2,
  CheckCircle,
  RefreshCw,
  Radio,
  Pencil,
  Search,
  Download,
  AlertTriangle,
  ChevronUp,
  ListChecks,
  CircleDot,
} from 'lucide-react';
import { authFetch } from '@/lib/api';
import MeetingLiveNotes from '../components/meetings/MeetingLiveNotes';
import CrossMeetingSearch from '../components/meetings/CrossMeetingSearch';
import CustomDictionaryPanel from '../components/meetings/CustomDictionaryPanel';
import {
  MeetingSession, MeetingChunk, MeetingDetail,
  apiFetch, formatDate, formatDuration, formatOffset, defaultTitle,
} from './utils';

// ===== Web Speech API 型宣言 =====
interface SpeechRecognitionEvent extends Event { results: SpeechRecognitionResultList; resultIndex: number; }
interface SpeechRecognitionErrorEvent extends Event { error: string; }
declare global {
  interface Window { SpeechRecognition: any; webkitSpeechRecognition: any; }
}

type Phase = 'list' | 'recording' | 'done';

// ===== 会議詳細モーダル =====

function MeetingDetailModal({
  sessionId,
  onClose,
}: {
  sessionId: number;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<MeetingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [notes, setNotes] = useState('');
  const [notesDirty, setNotesDirty] = useState(false);
  const [notesSaving, setNotesSaving] = useState(false);
  const [chunkNotes, setChunkNotes] = useState<Record<number, string>>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    apiFetch(`/api/meetings/${sessionId}`)
      .then((d) => {
        setDetail(d);
        setNotes(d?.notes ?? '');
        const cn: Record<number, string> = {};
        d?.chunks?.forEach((c: MeetingChunk) => { cn[c.id] = c.note ?? ''; });
        setChunkNotes(cn);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [sessionId]);

  // beforeunload for unsaved notes
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (notesDirty) { e.preventDefault(); }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [notesDirty]);

  const saveNotes = useCallback(async () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setNotesSaving(true);
    try {
      await apiFetch(`/api/meetings/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes }),
      });
      setNotesDirty(false);
    } catch (err) {
      console.error('notes save error:', err);
      alert('メモの保存に失敗しました');
    } finally {
      setNotesSaving(false);
    }
  }, [sessionId, notes]);

  const handleNotesChange = (val: string) => {
    setNotes(val);
    setNotesDirty(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => saveNotes(), 2000);
  };

  const handleNotesBlur = () => {
    if (notesDirty) {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      saveNotes();
    }
  };

  const saveChunkNote = async (chunkId: number, note: string) => {
    try {
      await apiFetch(`/api/meetings/chunks/${chunkId}/note`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note }),
      });
    } catch (err) {
      console.error('chunk note save error:', err);
      alert('チャンクメモの保存に失敗しました');
    }
  };

  const toggleChunk = (id: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleExport = () => {
    window.open(`/api/meetings/${sessionId}/export`, '_blank');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">
              {detail?.title ?? '読み込み中...'}
            </h2>
            {detail && (
              <p className="text-sm text-gray-400 mt-0.5">{formatDate(detail.created_at)}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {detail && (
              <button
                onClick={handleExport}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                title="Markdownでエクスポート"
              >
                <Download className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 rounded-lg transition-colors"
            >
              閉じる
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
          </div>
        ) : !detail ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">読み込みエラー</div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6 space-y-5">
            <div className="grid grid-cols-2 gap-3 text-sm">
              {detail.project_name && (
                <div className="flex items-center gap-2 text-gray-600">
                  <FolderOpen className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  {detail.project_name}
                </div>
              )}
              {detail.participants && (
                <div className="flex items-center gap-2 text-gray-600">
                  <Users className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  {detail.participants}
                </div>
              )}
            </div>

            {detail.summary && (
              <div className="bg-blue-50 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-blue-700 mb-2">AI サマリー</h3>
                <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                  {detail.summary}
                </p>
              </div>
            )}

            {/* セッションメモ */}
            <div className="bg-amber-50 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-amber-700 mb-2 flex items-center gap-2">
                メモ
                {notesSaving && <Loader2 className="w-3 h-3 animate-spin text-amber-500" />}
              </h3>
              <textarea
                value={notes}
                onChange={(e) => handleNotesChange(e.target.value)}
                onBlur={handleNotesBlur}
                placeholder="議事メモ、決定事項、アクションアイテム..."
                className="w-full min-h-[80px] px-3 py-2 rounded-lg border border-amber-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-300 focus:border-transparent resize-y"
              />
            </div>

            {detail.chunks.length > 0 ? (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">
                  文字起こし ({detail.chunks.length} チャンク)
                </h3>
                <div className="space-y-2">
                  {detail.chunks.map((chunk) => (
                    <div key={chunk.id} className="border border-gray-200 rounded-xl overflow-hidden">
                      <button
                        onClick={() => toggleChunk(chunk.id)}
                        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
                      >
                        <span className="text-sm font-medium text-gray-700">
                          チャンク {chunk.chunk_index + 1}
                          {chunk.start_offset_sec != null && chunk.start_offset_sec > 0 && (
                            <span className="ml-2 text-xs text-blue-500 font-mono">
                              {formatOffset(chunk.start_offset_sec)}
                            </span>
                          )}
                          <span className="ml-2 text-xs text-gray-400">
                            {formatDate(chunk.created_at)}
                          </span>
                        </span>
                        {expanded.has(chunk.id)
                          ? <ChevronDown className="w-4 h-4 text-gray-400" />
                          : <ChevronRight className="w-4 h-4 text-gray-400" />
                        }
                      </button>
                      {expanded.has(chunk.id) && (
                        <div className="px-4 pb-4 space-y-3">
                          <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                            {chunk.transcript}
                          </p>
                          <textarea
                            value={chunkNotes[chunk.id] ?? ''}
                            onChange={(e) => setChunkNotes(prev => ({ ...prev, [chunk.id]: e.target.value }))}
                            onBlur={() => saveChunkNote(chunk.id, chunkNotes[chunk.id] ?? '')}
                            placeholder="このチャンクへのメモ..."
                            className="w-full min-h-[40px] px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent resize-y"
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-400">文字起こしデータがありません</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ===== 会議一覧カード =====

function MeetingCard({
  session,
  onClick,
}: {
  session: MeetingSession;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md hover:border-blue-200 transition-all"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-800 truncate">{session.title}</p>
          <div className="flex flex-wrap gap-3 mt-1.5 text-xs text-gray-400">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDate(session.created_at)}
            </span>
            {session.project_name && (
              <span className="flex items-center gap-1">
                <FolderOpen className="w-3 h-3" />
                {session.project_name}
              </span>
            )}
            {session.participants && (
              <span className="flex items-center gap-1">
                <Users className="w-3 h-3" />
                {session.participants}
              </span>
            )}
          </div>
          {session.summary && (
            <p className="mt-2 text-xs text-gray-500 line-clamp-2">{session.summary}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
            {session.chunk_count ?? 0} チャンク
          </span>
          {session.summary && (
            <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full">
              サマリーあり
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

// ===== メタデータフォーム =====

function MetaForm({
  title, setTitle,
  project, setProject,
  participants, setParticipants,
  notes, setNotes,
  series, setSeries,
  onSave,
  saving,
}: {
  title: string; setTitle: (v: string) => void;
  project: string; setProject: (v: string) => void;
  participants: string; setParticipants: (v: string) => void;
  notes: string; setNotes: (v: string) => void;
  series: string; setSeries: (v: string) => void;
  onSave: () => void;
  saving: boolean;
}) {
  const [seriesList, setSeriesList] = useState<string[]>([]);
  const [projectsList, setProjectsList] = useState<{id: string; name: string}[]>([]);

  useEffect(() => {
    authFetch('/api/meetings/series').then(r => r.ok ? r.json() : []).then(setSeriesList).catch(() => {});
    authFetch('/api/projects/master').then(r => r.ok ? r.json() : []).then(setProjectsList).catch(() => {});
  }, []);

  return (
    <div className="space-y-3">
      <input
        type="text"
        value={title}
        onChange={e => setTitle(e.target.value)}
        placeholder="会議タイトル（空欄可）"
        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-transparent"
      />
      <div className="grid grid-cols-2 gap-2">
        <div className="relative">
          <input
            type="text"
            value={project}
            onChange={e => setProject(e.target.value)}
            list="project-list"
            placeholder="プロジェクト名"
            className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-transparent"
          />
          <datalist id="project-list">
            {projectsList.map(p => <option key={p.id} value={p.name} />)}
          </datalist>
        </div>
        <div className="relative">
          <input
            type="text"
            value={series}
            onChange={e => setSeries(e.target.value)}
            list="series-list"
            placeholder="シリーズ (例: OAC定例)"
            className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-transparent"
          />
          <datalist id="series-list">
            {seriesList.map(s => <option key={s} value={s} />)}
          </datalist>
        </div>
      </div>
      <input
        type="text"
        value={participants}
        onChange={e => setParticipants(e.target.value)}
        placeholder="参加者（任意、カンマ区切り）"
        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-transparent"
      />
      <textarea
        value={notes}
        onChange={e => setNotes(e.target.value)}
        placeholder="議事メモ、決定事項、アクションアイテム..."
        className="w-full min-h-[60px] px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-transparent resize-y"
      />
      <button
        onClick={onSave}
        disabled={saving}
        className="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm hover:bg-gray-200 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
      >
        {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
        保存
      </button>
    </div>
  );
}

// ===== メインページ =====

export default function MeetingsPage() {
  const [phase, setPhase] = useState<Phase>('list');
  const [sessions, setSessions] = useState<MeetingSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [detailId, setDetailId] = useState<number | null>(null);

  // 検索
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // メタデータ
  const [metaTitle, setMetaTitle] = useState('');
  const [metaProject, setMetaProject] = useState('');
  const [metaParticipants, setMetaParticipants] = useState('');
  const [metaNotes, setMetaNotes] = useState('');
  const [metaSeries, setMetaSeries] = useState('');
  const [metaSaving, setMetaSaving] = useState(false);
  const [carryForward, setCarryForward] = useState<any[]>([]);

  // Recording
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [chunkIndex, setChunkIndex] = useState(0);
  const [transcripts, setTranscripts] = useState<string[]>([]);
  const [sendingChunk, setSendingChunk] = useState(false);
  const [chunkError, setChunkError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chunkIndexRef = useRef(0);
  const isRecordingRef = useRef(false);
  const elapsedRef = useRef(0);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // Web Speech API — committed buffer pattern
  const recognitionRef = useRef<InstanceType<typeof window.SpeechRecognition> | null>(null);
  const [speechSupported, setSpeechSupported] = useState<boolean | null>(null);
  const [speechInterim, setSpeechInterim] = useState('');
  const [speechFinal, setSpeechFinal] = useState('');
  const [speechError, setSpeechError] = useState<string | null>(null);
  const speechCommittedRef = useRef('');
  const speechFinalRef = useRef('');
  const speechErrorCountRef = useRef(0);

  // Done
  const [summary, setSummary] = useState('');
  const [finalizing, setFinalizing] = useState(false);

  // 折りたたみ状態
  const [speechCollapsed, setSpeechCollapsed] = useState(false);
  const [geminiCollapsed, setGeminiCollapsed] = useState(true);
  const [metaCollapsed, setMetaCollapsed] = useState(true);

  // 会議一覧取得
  const fetchSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const data = await apiFetch('/api/meetings');
      setSessions(data ?? []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // 文字起こし末尾に自動スクロール
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcripts]);

  // ===== 検索 =====

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      fetchSessions();
      return;
    }
    setSearching(true);
    try {
      const data = await apiFetch(`/api/meetings/search?q=${encodeURIComponent(q)}`);
      setSessions(data ?? []);
    } catch {
      // fallback to full list
      fetchSessions();
    } finally {
      setSearching(false);
    }
  }, [fetchSessions]);

  const handleSearchChange = (q: string) => {
    setSearchQuery(q);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => doSearch(q), 300);
  };

  // ===== メタデータ保存 =====

  const saveMetadata = async () => {
    if (!sessionId) {
      setStartError('セッションIDが見つかりません。録音を再開してください。');
      return;
    }
    setMetaSaving(true);
    try {
      await apiFetch(`/api/meetings/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: metaTitle.trim() || undefined,
          project_name: metaProject.trim() || undefined,
          participants: metaParticipants.trim() || undefined,
          notes: metaNotes.trim() || undefined,
          series_name: metaSeries.trim() || undefined,
        }),
      });
    } catch (err) {
      console.error('metadata save error:', err);
      setStartError(err instanceof Error ? err.message : '保存に失敗しました');
    } finally {
      setMetaSaving(false);
    }
  };

  // ===== チャンク送信 =====

  // チャンク送信キュー: 前のチャンクの送信完了を待ってから次を送る
  const chunkQueueRef = useRef<Promise<void>>(Promise.resolve());

  const sendChunk = useCallback(async (blob: Blob, sid: number) => {
    if (blob.size === 0) return;

    // キューに追加して順次実行（レースコンディション防止）
    chunkQueueRef.current = chunkQueueRef.current.then(async () => {
      const idx = chunkIndexRef.current;
      setSendingChunk(true);
      setChunkError(null);
      try {
        const fd = new FormData();
        fd.append('session_id', String(sid));
        fd.append('chunk_index', String(idx));
        fd.append('start_offset_sec', String(elapsedRef.current));
        fd.append('file', blob, `chunk_${idx}.webm`);
        const result = await authFetch('/api/meetings/chunk', {
          method: 'POST',
          body: fd,
          signal: AbortSignal.timeout(120000),
        });
        if (!result.ok) {
          const err = await result.json().catch(() => ({}));
          throw new Error((err as { detail?: string }).detail ?? `HTTP ${result.status}`);
        }
        const data = await result.json();
        if (data.transcript) {
          setTranscripts(prev => [...prev, data.transcript]);
        }
        chunkIndexRef.current = idx + 1;
        setChunkIndex(prev => prev + 1);
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'チャンク送信エラー';
        console.error('chunk send error:', msg);
        setChunkError(msg);
      } finally {
        setSendingChunk(false);
      }
    });
  }, []);

  // ===== 録音開始 =====

  const handleStartRecording = async () => {
    setStarting(true);
    try {
      const title = defaultTitle();
      const session: MeetingSession = await apiFetch('/api/meetings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      });
      setSessionId(session.id);
      setMetaTitle(title);
      setMetaProject('');
      setMetaParticipants('');
      setMetaSeries('');
      setCarryForward([]);
      setMetaNotes('');

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunkIndexRef.current = 0;
      setChunkIndex(0);
      setTranscripts([]);
      setElapsed(0);
      elapsedRef.current = 0;
      setChunkError(null);

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          sendChunk(e.data, session.id);
        }
      };
      recorder.start(5 * 60 * 1000);

      timerRef.current = setInterval(() => {
        setElapsed(prev => prev + 1);
        elapsedRef.current += 1;
      }, 1000);

      // Web Speech API — committed buffer pattern
      setSpeechFinal('');
      setSpeechInterim('');
      setSpeechError(null);
      speechCommittedRef.current = '';
      speechFinalRef.current = '';
      speechErrorCountRef.current = 0;

      const SpeechRecognitionClass =
        typeof window !== 'undefined'
          ? (window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null)
          : null;

      if (SpeechRecognitionClass) {
        setSpeechSupported(true);
        const recognition = new SpeechRecognitionClass();
        recognition.lang = 'ja-JP';
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = (event: SpeechRecognitionEvent) => {
          let interim = '';
          let sessionFinal = '';
          for (let i = 0; i < event.results.length; i++) {
            const result = event.results[i];
            if (result.isFinal) {
              sessionFinal += result[0].transcript;
            } else {
              interim += result[0].transcript;
            }
          }
          speechFinalRef.current = sessionFinal;
          setSpeechFinal(speechCommittedRef.current + sessionFinal);
          setSpeechInterim(interim);
        };

        recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
          if (event.error === 'no-speech') return;
          speechErrorCountRef.current += 1;
          if (speechErrorCountRef.current >= 5) {
            setSpeechError('音声認識で繰り返しエラーが発生しています。Gemini高精度版は引き続き動作します。');
          }
          if (event.error === 'network' || event.error === 'service-not-allowed') return;
          if (speechErrorCountRef.current < 5) {
            setSpeechError(`音声認識エラー: ${event.error}`);
          }
        };

        recognition.onend = () => {
          if (isRecordingRef.current) {
            // Commit current session's finals before restart
            speechCommittedRef.current = speechCommittedRef.current + speechFinalRef.current;
            speechFinalRef.current = '';
            setTimeout(() => {
              if (isRecordingRef.current) {
                try { recognition.start(); } catch (_) {}
              }
            }, 300);
          }
        };

        recognition.start();
        recognitionRef.current = recognition;
      } else {
        setSpeechSupported(false);
      }

      isRecordingRef.current = true;
      setPhase('recording');
    } catch (err) {
      console.error(err);
      setStartError(err instanceof Error ? err.message : '録音を開始できませんでした');
    } finally {
      setStarting(false);
    }
  };

  // ===== 録音停止 =====

  const stopRecording = async () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;

    if (recorder.state !== 'inactive') {
      recorder.requestData();
      recorder.stop();
    }
    streamRef.current?.getTracks().forEach(t => t.stop());
    if (timerRef.current) clearInterval(timerRef.current);
    isRecordingRef.current = false;
    try { recognitionRef.current?.stop(); } catch (_) {}
    recognitionRef.current = null;

    if (sessionId) {
      setFinalizing(true);
      setPhase('done');
      // Wait for any pending chunk sends to complete before finalizing
      await chunkQueueRef.current;
      try {
        await apiFetch(`/api/meetings/${sessionId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: metaTitle.trim() || undefined,
            project_name: metaProject.trim() || undefined,
            participants: metaParticipants.trim() || undefined,
            notes: metaNotes.trim() || undefined,
          series_name: metaSeries.trim() || undefined,
          }),
        });
        const result = await apiFetch(`/api/meetings/${sessionId}/finalize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        setSummary(result?.summary ?? '');
      } catch (err) {
        console.error(err);
        setSummary('サマリー生成に失敗しました');
      } finally {
        setFinalizing(false);
        fetchSessions();
      }
    }
  };

  // ===== リセット =====

  const resetToList = () => {
    try { recognitionRef.current?.stop(); } catch (_) {}
    recognitionRef.current = null;
    setPhase('list');
    setSessionId(null);
    setMetaTitle('');
    setMetaProject('');
    setMetaParticipants('');
    setMetaNotes('');
    setMetaSeries('');
    setCarryForward([]);
    setTranscripts([]);
    setSpeechFinal('');
    setSpeechInterim('');
    setSpeechError(null);
    setElapsed(0);
    setSummary('');
    setChunkError(null);
  };

  // ===== レンダリング =====

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ヘッダー */}
      <header className="bg-white border-b border-gray-200 px-4 md:px-8 py-4 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <Radio className="w-5 h-5 text-red-500" />
          <h1 className="text-lg font-bold text-gray-900">会議文字起こし</h1>
          {phase !== 'list' && (
            <button
              onClick={resetToList}
              className="ml-auto text-sm text-gray-500 hover:text-gray-700 transition-colors"
            >
              ← 一覧に戻る
            </button>
          )}
          {phase === 'list' && (
            <button
              onClick={fetchSessions}
              className="ml-auto p-2 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
              title="更新"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto p-4 md:p-8">

          {/* ===== 一覧フェーズ ===== */}
          {phase === 'list' && (
            <div className="space-y-4">
              {/* クロスRAG検索 */}
              <CrossMeetingSearch />

              {/* カスタム辞書 */}
              <CustomDictionaryPanel />

              {/* 録音開始ボタン */}
              <button
                onClick={() => { setStartError(null); handleStartRecording(); }}
                disabled={starting}
                className="w-full flex items-center justify-center gap-2 py-5 rounded-2xl border-2 border-dashed border-red-300 text-red-500 hover:bg-red-50 hover:border-red-400 disabled:opacity-50 transition-all font-medium text-base"
              >
                {starting ? (
                  <><Loader2 className="w-5 h-5 animate-spin" />準備中...</>
                ) : (
                  <><Mic className="w-5 h-5" />録音開始</>
                )}
              </button>
              {startError && (
                <div className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
                  {startError}
                </div>
              )}

              {/* 検索 */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  placeholder="会議を検索..."
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent bg-white"
                />
                {searching && (
                  <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 animate-spin" />
                )}
              </div>

              {/* 会議一覧 */}
              {loadingSessions ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="w-8 h-8 animate-spin text-gray-300" />
                </div>
              ) : sessions.length === 0 ? (
                <div className="text-center py-16 text-gray-400">
                  <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">
                    {searchQuery ? '該当する会議がありません' : 'まだ会議記録がありません'}
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm font-medium text-gray-500">
                    {searchQuery ? `検索結果 (${sessions.length}件)` : `過去の会議 (${sessions.length}件)`}
                  </p>
                  {sessions.map(s => (
                    <MeetingCard
                      key={s.id}
                      session={s}
                      onClick={() => setDetailId(s.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ===== Recording フェーズ ===== */}
          {phase === 'recording' && (
            <div className="space-y-4">
              {/* 録音ステータスカード */}
              <div className="bg-white rounded-2xl border-2 border-red-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-3 w-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
                    </span>
                    <span className="text-sm font-medium text-gray-600">録音中</span>
                  </div>
                  <span className="text-2xl font-mono font-bold text-gray-800 tabular-nums">
                    {formatDuration(elapsed)}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-xs text-gray-400 mb-5">
                  <Clock className="w-3.5 h-3.5" />
                  5分ごとに自動送信
                  {sendingChunk && (
                    <span className="flex items-center gap-1 text-blue-500 ml-2">
                      <Loader2 className="w-3 h-3 animate-spin" />送信中...
                    </span>
                  )}
                  {chunkIndex > 0 && !sendingChunk && (
                    <span className="text-green-600 ml-2">
                      {chunkIndex} 件送信済み
                    </span>
                  )}
                </div>

                {/* チャンク送信エラー */}
                {chunkError && (
                  <div className="flex items-center gap-2 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mb-4">
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                    {chunkError}
                  </div>
                )}

                <button
                  onClick={stopRecording}
                  className="w-full py-3 rounded-xl bg-gray-800 text-white text-sm font-semibold hover:bg-gray-900 transition-colors flex items-center justify-center gap-2"
                >
                  <Square className="w-4 h-4 fill-white" />
                  録音を停止してサマリーを生成
                </button>
                <button
                  onClick={() => {
                    if (window.confirm('録音が中断されます。チャットに戻りますか？')) {
                      mediaRecorderRef.current?.stop();
                      streamRef.current?.getTracks().forEach(t => t.stop());
                      if (timerRef.current) clearInterval(timerRef.current);
                      window.location.href = '/';
                    }
                  }}
                  className="w-full py-2 text-sm text-gray-400 hover:text-gray-600 transition-colors"
                >
                  ← チャットに戻る
                </button>
              </div>

              {/* キャリーフォワード（同シリーズの未完了タスク） */}
              {carryForward.length > 0 && (
                <div className="bg-amber-50 rounded-2xl border border-amber-200 p-4">
                  <h3 className="text-sm font-semibold text-amber-700 mb-2 flex items-center gap-2">
                    <ListChecks className="w-4 h-4" />
                    前回からの未完了タスク ({carryForward.length}件)
                  </h3>
                  <div className="space-y-1.5">
                    {carryForward.map((t: any) => (
                      <div key={t.id} className="flex items-center gap-2 text-sm">
                        <CircleDot className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                        <span className="text-gray-700 flex-1 truncate">{t.title}</span>
                        {t.assignee_name && <span className="text-xs text-gray-400">{t.assignee_name}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ライブメモ（メイン操作エリア） */}
              {sessionId && (
                <MeetingLiveNotes
                  sessionId={sessionId}
                  elapsedSec={elapsed}
                />
              )}

              {/* Web Speech API — リアルタイム速報（折りたたみ可） */}
              <div className="bg-white rounded-2xl border border-gray-200">
                <button
                  onClick={() => setSpeechCollapsed(!speechCollapsed)}
                  className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors rounded-2xl"
                >
                  <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                    リアルタイム（Web Speech）
                    {(speechFinal || speechInterim) && !speechCollapsed && (
                      <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                    )}
                  </h3>
                  {speechCollapsed ? <ChevronRight className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </button>
                {!speechCollapsed && (
                  <div className="px-5 pb-4">
                    {speechSupported === false ? (
                      <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
                        Web Speech APIは非対応です。Geminiのみで文字起こしします。
                      </p>
                    ) : speechError ? (
                      <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">{speechError}</p>
                    ) : (speechFinal || speechInterim) ? (
                      <div className="max-h-48 overflow-y-auto text-sm leading-relaxed">
                        <span className="text-gray-800">{speechFinal}</span>
                        {speechInterim && (
                          <span className="text-gray-400 italic">{speechInterim}</span>
                        )}
                      </div>
                    ) : (
                      <div className="py-4 text-center">
                        <p className="text-sm text-gray-400">話し始めると文字起こしが表示されます</p>
                        <div className="flex justify-center gap-1 mt-2">
                          {[0, 1, 2].map(i => (
                            <span key={i} className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"
                              style={{ animationDelay: `${i * 0.15}s` }} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Gemini — 高精度版（折りたたみ可） */}
              <div className="bg-white rounded-2xl border border-gray-200">
                <button
                  onClick={() => setGeminiCollapsed(!geminiCollapsed)}
                  className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors rounded-2xl"
                >
                  <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                    Gemini高精度版
                    {sendingChunk && (
                      <span className="flex items-center gap-1 text-blue-500 text-xs font-normal">
                        <Loader2 className="w-3 h-3 animate-spin" />処理中...
                      </span>
                    )}
                    {chunkIndex > 0 && (
                      <span className="text-xs text-gray-400 font-normal">{chunkIndex}件</span>
                    )}
                  </h3>
                  {geminiCollapsed ? <ChevronRight className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </button>
                {!geminiCollapsed && (
                  <div className="px-5 pb-4">
                    {transcripts.length === 0 ? (
                      <div className="py-4 text-center">
                        <p className="text-sm text-gray-400">5分ごとに高精度版が表示されます</p>
                      </div>
                    ) : (
                      <div className="space-y-3 max-h-64 overflow-y-auto">
                        {transcripts.map((text, i) => (
                          <div key={i} className="border-l-2 border-blue-200 pl-3">
                            <p className="text-xs text-gray-400 mb-1">チャンク {i + 1}</p>
                            <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{text}</p>
                          </div>
                        ))}
                        <div ref={transcriptEndRef} />
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* メタデータ + メモ入力（折りたたみ可） */}
              <div className="bg-white rounded-2xl border border-gray-200">
                <button
                  onClick={() => setMetaCollapsed(!metaCollapsed)}
                  className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors rounded-2xl"
                >
                  <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                    <Pencil className="w-4 h-4 text-gray-400" />
                    会議情報
                  </h3>
                  {metaCollapsed ? <ChevronRight className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </button>
                {!metaCollapsed && (
                  <div className="px-5 pb-4">
                    <MetaForm
                      title={metaTitle} setTitle={setMetaTitle}
                      project={metaProject} setProject={setMetaProject}
                      participants={metaParticipants} setParticipants={setMetaParticipants}
                      notes={metaNotes} setNotes={setMetaNotes}
                      series={metaSeries} setSeries={setMetaSeries}
                      onSave={saveMetadata}
                      saving={metaSaving}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ===== Done フェーズ ===== */}
          {phase === 'done' && (
            <div className="space-y-4">
              {/* 完了バナー */}
              <div className="bg-green-50 border border-green-200 rounded-2xl p-5 flex items-center gap-3">
                <CheckCircle className="w-6 h-6 text-green-500 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-green-800">録音完了</p>
                  <p className="text-sm text-green-600">{formatDuration(elapsed)}</p>
                </div>
              </div>

              {/* メタデータ + メモ編集 */}
              <MetaForm
                title={metaTitle} setTitle={setMetaTitle}
                project={metaProject} setProject={setMetaProject}
                participants={metaParticipants} setParticipants={setMetaParticipants}
                notes={metaNotes} setNotes={setMetaNotes}
                series={metaSeries} setSeries={setMetaSeries}
                onSave={saveMetadata}
                saving={metaSaving}
              />

              {/* 文字起こし */}
              {transcripts.length > 0 && (
                <div className="bg-white rounded-2xl border border-gray-200 p-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3">文字起こし</h3>
                  <div className="space-y-3 max-h-60 overflow-y-auto">
                    {transcripts.map((text, i) => (
                      <div key={i} className="border-l-2 border-gray-200 pl-3">
                        <p className="text-xs text-gray-400 mb-1">チャンク {i + 1}</p>
                        <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                          {text}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI サマリー */}
              <div className="bg-white rounded-2xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  AI サマリー
                  {finalizing && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
                </h3>
                {finalizing ? (
                  <div className="py-6 text-center text-sm text-gray-400">
                    Gemini がサマリーを生成しています...
                  </div>
                ) : summary ? (
                  <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {summary}
                  </p>
                ) : (
                  <p className="text-sm text-gray-400">
                    サマリーがありません（文字起こしデータが空の可能性があります）
                  </p>
                )}
              </div>

              <button
                onClick={resetToList}
                className="w-full py-3 rounded-xl bg-gray-800 text-white text-sm font-semibold hover:bg-gray-900 transition-colors"
              >
                一覧に戻る
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 会議詳細モーダル */}
      {detailId != null && (
        <MeetingDetailModal
          sessionId={detailId}
          onClose={() => setDetailId(null)}
        />
      )}
    </div>
  );
}
