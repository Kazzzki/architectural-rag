'use client';

import Link from 'next/link';
import { Clock, Users, Trash2, Loader2, AlertTriangle, CheckCircle } from 'lucide-react';

interface MeetingSummary {
  id: string;
  title: string;
  meeting_date: string | null;
  duration_sec: number | null;
  participants: string[];
  original_filename: string;
  summary: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

interface Props {
  meeting: MeetingSummary;
  onDelete: (id: string) => void;
}

function formatDuration(sec: number | null): string {
  if (!sec) return '';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m > 0 ? `${m}分${s > 0 ? s + '秒' : ''}` : `${s}秒`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('ja-JP', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

const statusConfig: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  transcribing: {
    icon: <Loader2 className="w-4 h-4 animate-spin" />,
    label: '文字起こし中',
    color: 'text-blue-600',
  },
  generating: {
    icon: <Loader2 className="w-4 h-4 animate-spin" />,
    label: '議事録生成中',
    color: 'text-indigo-600',
  },
  completed: {
    icon: <CheckCircle className="w-4 h-4" />,
    label: '完了',
    color: 'text-green-600',
  },
  error: {
    icon: <AlertTriangle className="w-4 h-4" />,
    label: 'エラー',
    color: 'text-red-600',
  },
};

export default function MeetingCard({ meeting, onDelete }: Props) {
  const sc = statusConfig[meeting.status] || statusConfig.completed;
  const isClickable = meeting.status !== 'transcribing';

  const content = (
    <div className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-semibold text-gray-900 truncate">{meeting.title}</h3>
            <span className={`flex items-center gap-1 text-xs font-medium ${sc.color}`}>
              {sc.icon} {sc.label}
            </span>
          </div>

          {meeting.summary && (
            <p className="text-sm text-gray-600 line-clamp-2 mb-2">{meeting.summary}</p>
          )}

          {meeting.error_message && (
            <p className="text-sm text-red-500 mb-2">{meeting.error_message}</p>
          )}

          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span>{formatDate(meeting.created_at)}</span>
            {meeting.duration_sec && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatDuration(meeting.duration_sec)}
              </span>
            )}
            {meeting.participants.length > 0 && (
              <span className="flex items-center gap-1">
                <Users className="w-3 h-3" />
                {meeting.participants.length}名
              </span>
            )}
          </div>
        </div>

        <button
          onClick={e => { e.preventDefault(); e.stopPropagation(); onDelete(meeting.id); }}
          className="p-2 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors ml-2"
          title="削除"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );

  if (isClickable) {
    return <Link href={`/meetings/${meeting.id}`}>{content}</Link>;
  }
  return content;
}
