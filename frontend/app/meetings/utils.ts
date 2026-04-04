import { authFetch } from '@/lib/api';

// ===== 型定義 =====

export interface MeetingSession {
  id: number;
  project_name?: string;
  title: string;
  participants?: string;
  summary?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
  chunk_count?: number;
}

export interface MeetingChunk {
  id: number;
  session_id: number;
  chunk_index: number;
  transcript: string;
  note?: string;
  start_offset_sec?: number;
  created_at: string;
}

export interface MeetingDetail extends MeetingSession {
  chunks: MeetingChunk[];
  full_transcript: string;
}

// ===== API =====

export async function apiFetch(path: string, opts?: RequestInit) {
  const res = await authFetch(path, {
    ...opts,
    signal: opts?.signal ?? AbortSignal.timeout(15000),
  });
  if (res.status === 204) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ===== ユーティリティ =====

export function formatDate(iso: string) {
  return new Date(iso).toLocaleString('ja-JP', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

export function formatDuration(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function formatOffset(sec?: number | null): string {
  if (sec == null || sec < 0) return '';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function defaultTitle() {
  const now = new Date();
  const y = now.getFullYear();
  const mo = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  const h = String(now.getHours()).padStart(2, '0');
  const mi = String(now.getMinutes()).padStart(2, '0');
  return `会議_${y}-${mo}-${d}_${h}:${mi}`;
}
