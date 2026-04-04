'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft, FileAudio, Clock, Users, CheckCircle2,
  AlertTriangle, ListChecks, CircleDot, RefreshCw, Loader2,
  Pencil, Save, X, ClipboardList,
} from 'lucide-react';
import { authFetch } from '@/lib/api';
import MeetingTimeline from '../../components/meetings/MeetingTimeline';
import EntityLinksPanel from '../../components/meetings/EntityLinksPanel';
import MeetingAudioPlayer from '../../components/meetings/MeetingAudioPlayer';

interface MeetingDetail {
  id: string;
  title: string;
  meeting_date: string | null;
  duration_sec: number | null;
  participants: string[];
  original_filename: string;
  full_transcript: string;
  summary: string | null;
  agenda_items: { topic: string; summary: string; details: string }[];
  decisions: { content: string; by: string }[];
  action_items: { task: string; assignee: string; deadline: string }[];
  open_issues: { content: string; context: string }[];
  status: string;
  error_message: string | null;
  project_name: string | null;
  created_at: string;
  updated_at: string;
}

type TabId = 'minutes' | 'timeline' | 'transcript';

function formatDuration(sec: number | null): string {
  if (!sec) return '-';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m > 0 ? `${m}分${s > 0 ? s + '秒' : ''}` : `${s}秒`;
}

export default function MeetingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const meetingId = params.id as string;

  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId>('minutes');
  const [regenerating, setRegenerating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editSummary, setEditSummary] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [issueCandidates, setIssueCandidates] = useState<any[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [createdIssues, setCreatedIssues] = useState<Set<number>>(new Set());
  const [extractingTasks, setExtractingTasks] = useState(false);
  const [taskCandidates, setTaskCandidates] = useState<any[]>([]);
  const [createdTasks, setCreatedTasks] = useState<Set<number>>(new Set());
  const [audioSeekSec, setAudioSeekSec] = useState<number | undefined>(undefined);
  const [audioCurrentSec, setAudioCurrentSec] = useState(0);

  const fetchMeeting = useCallback(async () => {
    try {
      const res = await authFetch(`/api/meetings/${meetingId}`);
      if (res.ok) {
        const data = await res.json();
        setMeeting(data);
        setEditSummary(data.summary || '');
        setEditTitle(data.title || '');
      } else if (res.status === 404) {
        router.push('/meetings');
      }
    } catch (e) {
      console.error('Failed to fetch meeting:', e);
    } finally {
      setLoading(false);
    }
  }, [meetingId, router]);

  useEffect(() => {
    fetchMeeting();
  }, [fetchMeeting]);

  // ポーリング（処理中の場合）
  useEffect(() => {
    if (!meeting || (meeting.status !== 'transcribing' && meeting.status !== 'generating')) return;
    const timer = setInterval(fetchMeeting, 3000);
    return () => clearInterval(timer);
  }, [meeting, fetchMeeting]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const res = await authFetch(`/api/meetings/${meetingId}/regenerate`, { method: 'POST' });
      if (res.ok) {
        fetchMeeting();
      }
    } catch (e) {
      console.error('Failed to regenerate:', e);
    } finally {
      setRegenerating(false);
    }
  };

  const handleSaveEdit = async () => {
    try {
      const res = await authFetch(`/api/meetings/${meetingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitle, summary: editSummary }),
      });
      if (res.ok) {
        setEditing(false);
        fetchMeeting();
      }
    } catch (e) {
      console.error('Failed to save:', e);
    }
  };

  const handleExtractIssues = async () => {
    setExtracting(true);
    try {
      const res = await authFetch(`/api/meetings/${meetingId}/extract-issues`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setIssueCandidates(data.candidates || []);
      }
    } catch (e) {
      console.error('Failed to extract issues:', e);
    } finally {
      setExtracting(false);
    }
  };

  const handleCreateIssue = async (idx: number) => {
    const c = issueCandidates[idx];
    if (!c) return;
    const projectName = meeting?.project_name || prompt('プロジェクト名を入力:');
    if (!projectName) return;
    try {
      const res = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_input: c.raw_input,
          project_name: projectName,
        }),
      });
      if (res.ok) {
        setCreatedIssues(prev => new Set([...prev, idx]));
      }
    } catch (e) {
      console.error('Failed to create issue:', e);
    }
  };

  const handleExtractTasks = async () => {
    setExtractingTasks(true);
    try {
      const res = await authFetch('/api/tasks/extract-from-meeting', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting_id: parseInt(meetingId) }),
      });
      if (res.ok) {
        const data = await res.json();
        setTaskCandidates(data.proposed_tasks ?? []);
      }
    } catch (e) {
      console.error('Failed to extract tasks:', e);
    } finally {
      setExtractingTasks(false);
    }
  };

  const handleCreateTask = async (idx: number) => {
    const t = taskCandidates[idx];
    if (!t) return;
    try {
      const res = await authFetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: t.title,
          description: t.description,
          assignee_name: t.assignee_name,
          due_date: t.due_date,
          priority: t.priority || 'medium',
          status: 'todo',
          project_name: meeting?.project_name || undefined,
        }),
      });
      if (res.ok) {
        setCreatedTasks(prev => new Set([...prev, idx]));
      }
    } catch (e) {
      console.error('Failed to create task:', e);
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

  const isProcessing = meeting.status === 'transcribing' || meeting.status === 'generating';

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
                {meeting.meeting_date && <span>{meeting.meeting_date}</span>}
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {formatDuration(meeting.duration_sec)}
                </span>
                {meeting.participants.length > 0 && (
                  <span className="flex items-center gap-1">
                    <Users className="w-3.5 h-3.5" />
                    {meeting.participants.join(', ')}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!isProcessing && meeting.status === 'completed' && (
              <>
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
                  onClick={handleRegenerate}
                  disabled={regenerating}
                  className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${regenerating ? 'animate-spin' : ''}`} /> 再生成
                </button>
              </>
            )}
            <StatusBadge status={meeting.status} />
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Processing State */}
        {isProcessing && (
          <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-6 mb-6 flex items-center gap-4">
            <Loader2 className="w-6 h-6 text-indigo-500 animate-spin flex-shrink-0" />
            <div>
              <p className="font-medium text-indigo-800">
                {meeting.status === 'transcribing' ? '音声を文字起こし中...' : '議事録を生成中...'}
              </p>
              <p className="text-sm text-indigo-600 mt-1">
                完了まで少々お待ちください。このページは自動更新されます。
              </p>
            </div>
          </div>
        )}

        {/* Error State */}
        {meeting.status === 'error' && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 mb-6">
            <div className="flex items-center gap-2 text-red-700 font-medium">
              <AlertTriangle className="w-5 h-5" />
              エラーが発生しました
            </div>
            <p className="text-sm text-red-600 mt-2">{meeting.error_message}</p>
          </div>
        )}

        {/* Audio Player */}
        {meeting.status === 'completed' && (
          <div className="mb-6">
            <MeetingAudioPlayer
              sessionId={parseInt(meetingId)}
              seekToSec={audioSeekSec}
              onTimeUpdate={setAudioCurrentSec}
            />
          </div>
        )}

        {/* Tabs */}
        {meeting.status === 'completed' && (
          <>
            <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
              <button
                onClick={() => setActiveTab('minutes')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'minutes'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                議事録
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

            {activeTab === 'minutes' ? (
              <div className="space-y-6">
                {/* Summary */}
                {meeting.summary && (
                  <Section title="概要">
                    {editing ? (
                      <textarea
                        value={editSummary}
                        onChange={e => setEditSummary(e.target.value)}
                        rows={4}
                        className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 outline-none"
                      />
                    ) : (
                      <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{meeting.summary}</p>
                    )}
                  </Section>
                )}

                {/* Agenda Items */}
                {meeting.agenda_items.length > 0 && (
                  <Section title="議題">
                    <div className="space-y-4">
                      {meeting.agenda_items.map((item, i) => (
                        <div key={i} className="border-l-2 border-indigo-300 pl-4">
                          <h4 className="font-medium text-gray-800">{item.topic}</h4>
                          <p className="text-sm text-gray-600 mt-1">{item.summary}</p>
                          {item.details && (
                            <p className="text-sm text-gray-500 mt-1">{item.details}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {/* Decisions */}
                {meeting.decisions.length > 0 && (
                  <Section title="決定事項" icon={<CheckCircle2 className="w-5 h-5 text-green-600" />}>
                    <ul className="space-y-2">
                      {meeting.decisions.map((d, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                          <div>
                            <span className="text-gray-700">{d.content}</span>
                            {d.by && <span className="text-sm text-gray-500 ml-2">({d.by})</span>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </Section>
                )}

                {/* Action Items */}
                {meeting.action_items.length > 0 && (
                  <Section title="アクションアイテム" icon={<ListChecks className="w-5 h-5 text-blue-600" />}>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-gray-500 border-b">
                            <th className="pb-2 pr-4">タスク</th>
                            <th className="pb-2 pr-4">担当者</th>
                            <th className="pb-2">期限</th>
                          </tr>
                        </thead>
                        <tbody>
                          {meeting.action_items.map((a, i) => (
                            <tr key={i} className="border-b border-gray-100">
                              <td className="py-2 pr-4 text-gray-700">{a.task}</td>
                              <td className="py-2 pr-4 text-gray-600">{a.assignee || '-'}</td>
                              <td className="py-2 text-gray-600">{a.deadline || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Section>
                )}

                {/* Open Issues */}
                {meeting.open_issues.length > 0 && (
                  <Section title="未解決事項" icon={<CircleDot className="w-5 h-5 text-amber-600" />}>
                    <ul className="space-y-2">
                      {meeting.open_issues.map((o, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <CircleDot className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                          <div>
                            <span className="text-gray-700">{o.content}</span>
                            {o.context && (
                              <p className="text-sm text-gray-500 mt-0.5">{o.context}</p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </Section>
                )}
                {/* 課題に変換 */}
                {(meeting.action_items.length > 0 || meeting.open_issues.length > 0) && (
                  <div className="bg-white rounded-xl border border-gray-200 p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                        <ClipboardList className="w-4 h-4 text-indigo-600" />
                        課題因果グラフに追加
                      </h3>
                      <button
                        onClick={handleExtractIssues}
                        disabled={extracting}
                        className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-1"
                      >
                        {extracting ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                        候補を抽出
                      </button>
                    </div>
                    {issueCandidates.length > 0 && (
                      <div className="space-y-2">
                        {issueCandidates.map((c, i) => (
                          <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-gray-50">
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-gray-800 truncate">{c.title}</p>
                              <p className="text-xs text-gray-400">
                                {c.source === 'action_item' ? 'アクションアイテム' : '未解決事項'}
                                {c.assignee ? ` / ${c.assignee}` : ''}
                              </p>
                            </div>
                            {createdIssues.has(i) ? (
                              <span className="text-xs text-green-600 flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5" /> 追加済み
                              </span>
                            ) : (
                              <button
                                onClick={() => handleCreateIssue(i)}
                                className="text-xs px-2 py-1 border border-indigo-300 text-indigo-600 rounded-lg hover:bg-indigo-50"
                              >
                                追加
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    {issueCandidates.length === 0 && !extracting && (
                      <p className="text-xs text-gray-400">「候補を抽出」ボタンで議事録から課題候補を取り出せます</p>
                    )}
                  </div>
                )}
                {/* タスク抽出 */}
                <div className="bg-white rounded-xl border border-gray-200 p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                      <ListChecks className="w-4 h-4 text-gray-600" />
                      タスクとして抽出
                    </h3>
                    <button
                      onClick={handleExtractTasks}
                      disabled={extractingTasks}
                      className="text-xs px-3 py-1.5 bg-gray-800 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 flex items-center gap-1"
                    >
                      {extractingTasks ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                      タスクを抽出
                    </button>
                  </div>
                  {taskCandidates.length > 0 && (
                    <div className="space-y-2">
                      {taskCandidates.map((t: any, i: number) => (
                        <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-gray-50">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-gray-800 truncate">{t.title}</p>
                            <p className="text-xs text-gray-400">
                              {t.assignee_name ? `担当: ${t.assignee_name}` : ''}
                              {t.due_date ? ` / 期限: ${t.due_date}` : ''}
                              {t.priority ? ` / ${t.priority}` : ''}
                            </p>
                          </div>
                          {createdTasks.has(i) ? (
                            <span className="text-xs text-green-600 flex items-center gap-1">
                              <CheckCircle2 className="w-3.5 h-3.5" /> 追加済み
                            </span>
                          ) : (
                            <button
                              onClick={() => handleCreateTask(i)}
                              className="text-xs px-2 py-1 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-100"
                            >
                              タスク追加
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {taskCandidates.length === 0 && !extractingTasks && (
                    <p className="text-xs text-gray-400">「タスクを抽出」ボタンで議事録からアクションアイテムを抽出できます</p>
                  )}
                </div>

                {/* エンティティリンク + タグ (Phase 1B) */}
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
                <p className="text-gray-700 leading-relaxed whitespace-pre-wrap text-sm">
                  {meeting.full_transcript}
                </p>
              </div>
            )}
          </>
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

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; color: string }> = {
    transcribing: { label: '文字起こし中', color: 'bg-blue-100 text-blue-700' },
    generating: { label: '議事録生成中', color: 'bg-indigo-100 text-indigo-700' },
    completed: { label: '完了', color: 'bg-green-100 text-green-700' },
    error: { label: 'エラー', color: 'bg-red-100 text-red-700' },
  };
  const c = config[status] || { label: status, color: 'bg-gray-100 text-gray-700' };
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${c.color}`}>
      {c.label}
    </span>
  );
}
