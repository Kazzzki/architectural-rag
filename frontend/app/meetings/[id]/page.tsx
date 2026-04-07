'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Clock, Users, RefreshCw, Loader2,
  Pencil, Save, X, ListChecks, CheckCircle2,
  FolderOpen, ClipboardCopy, Check, CircleDot, ListTodo,
  MessageSquare, Target, AlertTriangle,
} from 'lucide-react';
import { authFetch } from '@/lib/api';
import { MeetingDetail, apiFetch, formatDate } from '../utils';
import MeetingTimeline from '../../components/meetings/MeetingTimeline';
import EntityLinksPanel from '../../components/meetings/EntityLinksPanel';
import MeetingAudioPlayer from '../../components/meetings/MeetingAudioPlayer';

type TabId = 'summary' | 'timeline' | 'transcript';

export default function MeetingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const meetingId = params.id as string;

  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId>('summary');
  const [regenerating, setRegenerating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editSummary, setEditSummary] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [extractingTasks, setExtractingTasks] = useState(false);
  const [createdTasks, setCreatedTasks] = useState<any[]>([]);
  const [audioSeekSec, setAudioSeekSec] = useState<number | undefined>(undefined);
  const [audioCurrentSec, setAudioCurrentSec] = useState(0);
  const [exported, setExported] = useState(false);
  const [pastDecisions, setPastDecisions] = useState<any[]>([]);
  const [showDecisions, setShowDecisions] = useState(false);
  const [liveNotes, setLiveNotes] = useState<any[]>([]);
  const [convertedNotes, setConvertedNotes] = useState<Record<number, string>>({});

  const fetchMeeting = useCallback(async () => {
    try {
      const [data, notes] = await Promise.all([
        apiFetch(`/api/meetings/${meetingId}`),
        apiFetch(`/api/meetings/${meetingId}/live-notes`).catch(() => []),
      ]);
      if (data) {
        setMeeting(data);
        setEditSummary(data.summary || '');
        setEditTitle(data.title || '');
      }
      setLiveNotes(notes || []);
    } catch (e) {
      console.error('Failed to fetch meeting:', e);
      router.push('/meetings');
    } finally {
      setLoading(false);
    }
  }, [meetingId, router]);

  const handleConvertNoteToIssue = async (note: any) => {
    try {
      const res = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: note.content, project_name: meeting?.project_name || 'default', skip_ai: true }),
      });
      if (res.ok) {
        const data = await res.json();
        setConvertedNotes(prev => ({ ...prev, [note.id]: `issue:${data.issue?.id || data.id}` }));
      }
    } catch (e) { console.error(e); }
  };

  const handleConvertNoteToTask = async (note: any) => {
    try {
      const res = await authFetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: note.content, source_meeting_id: parseInt(meetingId),
          source_type: 'meeting', project_name: meeting?.project_name,
          priority: note.note_type === 'risk' ? 'high' : 'medium', status: 'todo',
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setConvertedNotes(prev => ({ ...prev, [note.id]: `task:${data.id}` }));
      }
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    fetchMeeting();
  }, [fetchMeeting]);

  // BUG-3 fix: /regenerate -> /finalize
  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      await apiFetch(`/api/meetings/${meetingId}/finalize`, {
        method: 'POST',
        signal: AbortSignal.timeout(120000),
      });
      fetchMeeting();
    } catch (e) {
      console.error('Failed to regenerate:', e);
    } finally {
      setRegenerating(false);
    }
  };

  // BUG-2 fix: PUT -> PATCH
  const handleSaveEdit = async () => {
    try {
      await apiFetch(`/api/meetings/${meetingId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitle, summary: editSummary }),
      });
      setEditing(false);
      fetchMeeting();
    } catch (e) {
      console.error('Failed to save:', e);
    }
  };

  // BUG-5 fix: /api/tasks/extract-from-meeting -> /api/meetings/{id}/create-tasks
  const handleExtractTasks = async () => {
    setExtractingTasks(true);
    try {
      const data = await apiFetch(`/api/meetings/${meetingId}/create-tasks`, {
        method: 'POST',
        signal: AbortSignal.timeout(60000),
      });
      setCreatedTasks(data?.tasks_created || []);
    } catch (e) {
      console.error('Failed to extract tasks:', e);
    } finally {
      setExtractingTasks(false);
    }
  };

  const handleExportToClipboard = async () => {
    try {
      const res = await authFetch(`/api/meetings/${meetingId}/export`);
      if (res.ok) {
        const md = await res.text();
        await navigator.clipboard.writeText(md);
        setExported(true);
        setTimeout(() => setExported(false), 3000);
      }
    } catch (e) {
      console.error('Export failed:', e);
    }
  };

  const handleShowDecisions = async () => {
    if (showDecisions) { setShowDecisions(false); return; }
    try {
      const pn = meeting?.project_name;
      const url = pn ? `/api/meetings/decisions?project_name=${encodeURIComponent(pn)}` : '/api/meetings/decisions';
      const res = await authFetch(url);
      if (res.ok) {
        const data = await res.json();
        setPastDecisions(data);
        setShowDecisions(true);
      }
    } catch (e) {
      console.error('Failed to fetch decisions:', e);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!meeting) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.back()}
              className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              {editing ? (
                <input
                  value={editTitle}
                  onChange={e => setEditTitle(e.target.value)}
                  className="text-xl font-bold text-gray-900 border-b-2 border-indigo-400 outline-none bg-transparent"
                />
              ) : (
                <h1 className="text-xl font-bold text-gray-900">{meeting.title}</h1>
              )}
              <div className="flex items-center gap-4 text-sm text-gray-500 mt-1">
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {formatDate(meeting.created_at)}
                </span>
                {meeting.project_name && (
                  <span className="flex items-center gap-1">
                    <FolderOpen className="w-3.5 h-3.5" />
                    {meeting.project_name}
                  </span>
                )}
                {meeting.participants && (
                  <span className="flex items-center gap-1">
                    <Users className="w-3.5 h-3.5" />
                    {meeting.participants}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {editing ? (
              <>
                <button
                  onClick={handleSaveEdit}
                  className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
                >
                  <Save className="w-4 h-4" /> 保存
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="flex items-center gap-1 px-3 py-1.5 bg-gray-200 text-gray-700 text-sm rounded-lg hover:bg-gray-300"
                >
                  <X className="w-4 h-4" /> 取消
                </button>
              </>
            ) : (
              <button
                onClick={() => setEditing(true)}
                className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200"
              >
                <Pencil className="w-4 h-4" /> 編集
              </button>
            )}
            <button
              onClick={handleExportToClipboard}
              className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-700 text-sm rounded-full hover:bg-gray-200"
            >
              {exported ? <><Check className="w-4 h-4 text-green-600" /> コピー済み</> : <><ClipboardCopy className="w-4 h-4" /> Notionへ</>}
            </button>
            <button
              onClick={handleShowDecisions}
              className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded-full ${showDecisions ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
            >
              <CheckCircle2 className="w-4 h-4" /> 過去決定
            </button>
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-700 text-sm rounded-full hover:bg-gray-200 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${regenerating ? 'animate-spin' : ''}`} /> 再生成
            </button>
            {meeting.chunks.length > 0 && (
              <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">
                {meeting.chunks.length} チャンク
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Past Decisions Panel */}
        {showDecisions && (
          <div className="mb-6 bg-white border border-gray-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-600" />
              過去の決定事項 {meeting.project_name && <span className="text-xs text-gray-400">({meeting.project_name})</span>}
            </h3>
            {pastDecisions.length === 0 ? (
              <p className="text-sm text-gray-400">過去の決定事項はありません</p>
            ) : (
              <ul className="space-y-2 max-h-48 overflow-y-auto">
                {pastDecisions.map((d: any) => (
                  <li key={d.id} className="flex items-start gap-2 text-sm">
                    <span className="text-xs text-gray-400 font-mono shrink-0 mt-0.5">{d.meeting_date?.slice(0, 10)}</span>
                    <span className="text-gray-700">{d.content}</span>
                    <span className="text-xs text-gray-400 shrink-0">({d.meeting_title})</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Audio Player */}
        <div className="mb-6">
          <MeetingAudioPlayer
            sessionId={parseInt(meetingId)}
            seekToSec={audioSeekSec}
            onTimeUpdate={setAudioCurrentSec}
          />
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
          <button
            onClick={() => setActiveTab('summary')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'summary'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            サマリー
          </button>
          <button
            onClick={() => setActiveTab('timeline')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'timeline'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            タイムライン
          </button>
          <button
            onClick={() => setActiveTab('transcript')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'transcript'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            全文文字起こし
          </button>
        </div>

        {activeTab === 'summary' ? (
          <div className="space-y-6">
            {/* AI Summary */}
            {meeting.summary ? (
              <Section title="AI サマリー">
                {editing ? (
                  <textarea
                    value={editSummary}
                    onChange={e => setEditSummary(e.target.value)}
                    rows={8}
                    className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 outline-none"
                  />
                ) : (
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{meeting.summary}</p>
                )}
              </Section>
            ) : (
              <Section title="AI サマリー">
                <p className="text-gray-400 text-sm">
                  サマリーがありません。「再生成」ボタンでサマリーを生成できます。
                </p>
              </Section>
            )}

            {/* Notes */}
            {meeting.notes && (
              <Section title="メモ">
                <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{meeting.notes}</p>
              </Section>
            )}

            {/* Live Notes with Convert Buttons */}
            {liveNotes.length > 0 && (
              <Section title="ライブメモ">
                <div className="space-y-1.5">
                  {liveNotes.map((note: any) => {
                    const typeConfig: Record<string, { icon: typeof MessageSquare; label: string; color: string }> = {
                      memo: { icon: MessageSquare, label: 'メモ', color: 'text-gray-500' },
                      decision: { icon: CheckCircle2, label: '決定', color: 'text-green-600' },
                      action: { icon: Target, label: 'アクション', color: 'text-blue-600' },
                      risk: { icon: AlertTriangle, label: 'リスク', color: 'text-amber-600' },
                    };
                    const cfg = typeConfig[note.note_type] || typeConfig.memo;
                    const Icon = cfg.icon;
                    const ts = note.timestamp_sec != null
                      ? `${String(Math.floor(note.timestamp_sec / 60)).padStart(2, '0')}:${String(note.timestamp_sec % 60).padStart(2, '0')}`
                      : '';
                    return (
                      <div key={note.id} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-gray-50">
                        <span className="text-xs font-mono text-blue-500 w-12 text-right shrink-0">{ts}</span>
                        <Icon className={`w-3.5 h-3.5 shrink-0 ${cfg.color}`} />
                        <span className="flex-1 text-sm text-gray-700">{note.content}</span>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                          {convertedNotes[note.id] ? (
                            <span className="text-[10px] text-green-600 bg-green-50 px-1.5 py-0.5 rounded-full">
                              {convertedNotes[note.id].startsWith('issue:') ? `課題 #${convertedNotes[note.id].split(':')[1]}` : `タスク #${convertedNotes[note.id].split(':')[1]}`}
                            </span>
                          ) : (
                            <>
                              <button onClick={() => handleConvertNoteToIssue(note)} title="課題に登録" className="p-1 text-gray-400 hover:text-orange-600 hover:bg-orange-50 rounded">
                                <CircleDot className="w-3.5 h-3.5" />
                              </button>
                              <button onClick={() => handleConvertNoteToTask(note)} title="タスクに登録" className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded">
                                <ListTodo className="w-3.5 h-3.5" />
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Section>
            )}

            {/* Extract Tasks */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-gray-600" />
                  タスク自動作成
                </h3>
                <button
                  onClick={handleExtractTasks}
                  disabled={extractingTasks}
                  className="text-xs px-3 py-1.5 bg-gray-800 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 flex items-center gap-1"
                >
                  {extractingTasks ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                  タスクを作成
                </button>
              </div>
              {createdTasks.length > 0 && (
                <div className="space-y-2">
                  {createdTasks.map((t: any, i: number) => (
                    <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-gray-50">
                      <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-800 truncate">{t.title}</p>
                        <p className="text-xs text-gray-400">
                          {t.assignee ? `担当: ${t.assignee}` : ''}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {createdTasks.length === 0 && !extractingTasks && (
                <p className="text-xs text-gray-400">「タスクを作成」ボタンでサマリーからアクションアイテムを自動抽出してタスク登録します</p>
              )}
            </div>

            {/* Entity Links + Tags (Phase 1B) */}
            <EntityLinksPanel sessionId={parseInt(meetingId)} />
          </div>
        ) : activeTab === 'timeline' ? (
          /* Timeline Tab */
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <MeetingTimeline
              sessionId={parseInt(meetingId)}
              currentTimeSec={audioCurrentSec}
              onSeek={(sec) => setAudioSeekSec(sec)}
            />
          </div>
        ) : (
          /* Transcript Tab */
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            {meeting.full_transcript ? (
              <p className="text-gray-700 leading-relaxed whitespace-pre-wrap text-sm">
                {meeting.full_transcript}
              </p>
            ) : (
              <p className="text-gray-400 text-sm">文字起こしデータがありません</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function Section({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <h3 className="flex items-center gap-2 text-base font-semibold text-gray-800 mb-4">
        {icon}
        {title}
      </h3>
      {children}
    </div>
  );
}
