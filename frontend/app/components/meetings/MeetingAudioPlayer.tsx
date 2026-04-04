'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Play, Pause, Volume2, VolumeX } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface Props {
  sessionId: number;
  /** 外部からシーク位置を指定（秒） */
  seekToSec?: number;
  /** 現在の再生位置を親に通知 */
  onTimeUpdate?: (sec: number) => void;
}

export default function MeetingAudioPlayer({ sessionId, seekToSec, onTimeUpdate }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [hasAudio, setHasAudio] = useState<boolean | null>(null);
  const [muted, setMuted] = useState(false);

  // 音声ファイル存在チェック
  useEffect(() => {
    authFetch(`/api/meetings/${sessionId}/audio`, { method: 'HEAD' })
      .then(res => setHasAudio(res.ok))
      .catch(() => setHasAudio(false));
  }, [sessionId]);

  // 外部からのシーク
  useEffect(() => {
    if (seekToSec != null && audioRef.current) {
      audioRef.current.currentTime = seekToSec;
      if (!playing) {
        audioRef.current.play().catch(() => {});
        setPlaying(true);
      }
    }
  }, [seekToSec]);

  const handleTimeUpdate = useCallback(() => {
    if (audioRef.current) {
      const t = Math.floor(audioRef.current.currentTime);
      setCurrentTime(t);
      onTimeUpdate?.(t);
    }
  }, [onTimeUpdate]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch(() => {});
    }
    setPlaying(!playing);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = val;
      setCurrentTime(val);
    }
  };

  const fmt = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  };

  if (hasAudio === false) return null;
  if (hasAudio === null) return null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <audio
        ref={audioRef}
        src={`/api/meetings/${sessionId}/audio`}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
        onEnded={() => setPlaying(false)}
        muted={muted}
      />
      <div className="flex items-center gap-3">
        <button
          onClick={togglePlay}
          className="p-2 rounded-full bg-indigo-600 text-white hover:bg-indigo-700 transition-colors flex-shrink-0"
        >
          {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        </button>
        <span className="text-xs font-mono text-gray-500 w-12 text-right flex-shrink-0">
          {fmt(currentTime)}
        </span>
        <input
          type="range"
          min={0}
          max={duration || 0}
          value={currentTime}
          onChange={handleSeek}
          className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-indigo-600"
        />
        <span className="text-xs font-mono text-gray-400 w-12 flex-shrink-0">
          {fmt(duration)}
        </span>
        <button
          onClick={() => setMuted(!muted)}
          className="p-1.5 text-gray-400 hover:text-gray-600 rounded transition-colors flex-shrink-0"
        >
          {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}
