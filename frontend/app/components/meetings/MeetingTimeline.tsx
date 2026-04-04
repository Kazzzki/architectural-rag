'use client';

import { useEffect, useRef, useState } from 'react';
import { MessageSquare, CheckCircle2, Target, AlertTriangle, FileText, Search, Loader2 } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface TimelineEntry {
  type: 'chunk' | 'live_note';
  timestamp_sec: number;
  id: number;
  // chunk fields
  chunk_index?: number;
  transcript?: string;
  note?: string;
  // live_note fields
  content?: string;
  note_type?: string;
  created_at: string;
}

interface Props {
  sessionId: number;
  /** 音声再生中の現在位置（秒） */
  currentTimeSec?: number;
  /** タイムラインエントリクリック時 */
  onSeek?: (sec: number) => void;
}

const NOTE_ICONS: Record<string, typeof MessageSquare> = {
  memo: MessageSquare,
  decision: CheckCircle2,
  action: Target,
  risk: AlertTriangle,
};

const NOTE_COLORS: Record<string, string> = {
  memo: 'border-gray-300 bg-gray-50',
  decision: 'border-green-300 bg-green-50',
  action: 'border-blue-300 bg-blue-50',
  risk: 'border-amber-300 bg-amber-50',
};

function formatTime(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function MeetingTimeline({ sessionId, currentTimeSec, onSeek }: Props) {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const activeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    authFetch(`/api/meetings/${sessionId}/timeline`)
      .then(res => res.ok ? res.json() : [])
      .then(data => { setEntries(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [sessionId]);

  // 再生中に現在位置のエントリへスクロール
  useEffect(() => {
    if (currentTimeSec != null && activeRef.current) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [currentTimeSec]);

  const filtered = filter.trim()
    ? entries.filter(e => {
        const text = e.type === 'chunk' ? (e.transcript || '') : (e.content || '');
        return text.toLowerCase().includes(filter.toLowerCase());
      })
    : entries;

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-16 bg-gray-100 rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
        <p className="text-sm">タイムラインデータがありません</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 検索フィルタ */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="タイムライン内を検索..."
          className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent"
        />
      </div>

      {/* タイムラインエントリ */}
      <div className="space-y-2">
        {filtered.map((entry, idx) => {
          const isActive = currentTimeSec != null &&
            entry.timestamp_sec <= currentTimeSec &&
            (idx + 1 >= filtered.length || filtered[idx + 1].timestamp_sec > currentTimeSec);

          if (entry.type === 'chunk') {
            return (
              <div
                key={`chunk-${entry.id}`}
                ref={isActive ? activeRef : undefined}
                onClick={() => onSeek?.(entry.timestamp_sec)}
                className={`flex gap-3 p-3 rounded-xl border transition-colors cursor-pointer hover:bg-gray-50 ${
                  isActive ? 'border-blue-300 bg-blue-50' : 'border-gray-200 bg-white'
                }`}
              >
                <span className="text-xs font-mono text-blue-500 mt-1 flex-shrink-0 w-16 text-right">
                  {formatTime(entry.timestamp_sec)}
                </span>
                <FileText className="w-4 h-4 text-gray-400 mt-1 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-gray-400 mb-0.5">チャンク {(entry.chunk_index ?? 0) + 1}</p>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed line-clamp-3">
                    {entry.transcript}
                  </p>
                </div>
              </div>
            );
          }

          // live_note
          const noteType = entry.note_type || 'memo';
          const Icon = NOTE_ICONS[noteType] || MessageSquare;
          const colorClass = NOTE_COLORS[noteType] || NOTE_COLORS.memo;

          return (
            <div
              key={`note-${entry.id}`}
              ref={isActive ? activeRef : undefined}
              onClick={() => onSeek?.(entry.timestamp_sec)}
              className={`flex gap-3 p-3 rounded-xl border-l-4 transition-colors cursor-pointer hover:opacity-90 ${colorClass} ${
                isActive ? 'ring-2 ring-blue-300' : ''
              }`}
            >
              <span className="text-xs font-mono text-blue-500 mt-0.5 flex-shrink-0 w-16 text-right">
                {formatTime(entry.timestamp_sec)}
              </span>
              <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-gray-800 flex-1">{entry.content}</p>
            </div>
          );
        })}
      </div>

      {filter && filtered.length === 0 && (
        <p className="text-center text-sm text-gray-400 py-4">
          「{filter}」に一致するエントリがありません
        </p>
      )}
    </div>
  );
}
