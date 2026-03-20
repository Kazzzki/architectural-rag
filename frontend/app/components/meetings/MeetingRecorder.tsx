'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, Square, Loader2 } from 'lucide-react';
import { authFetch } from '@/lib/api';

// Web Speech API — TypeScript DOM型に含まれないためany経由で利用
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SpeechRecognitionAny = any;

interface Props {
  onUploaded: (id: string) => void;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function MeetingRecorder({ onUploaded }: Props) {
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Web Speech API (リアルタイム速報)
  const recognitionRef = useRef<SpeechRecognitionAny>(null);
  const [speechSupported, setSpeechSupported] = useState<boolean | null>(null);
  const [speechFinal, setSpeechFinal] = useState('');
  const [speechInterim, setSpeechInterim] = useState('');

  useEffect(() => {
    const SR = typeof window !== 'undefined'
      ? ((window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition ?? null)
      : null;
    setSpeechSupported(!!SR);
  }, []);

  const startSpeechRecognition = useCallback(() => {
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (!SR) return;
    const recognition = new SR();
    recognition.lang = 'ja-JP';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event: any) => {
      let interim = '';
      let finalText = '';
      for (let i = 0; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      if (finalText) setSpeechFinal(prev => prev + finalText);
      setSpeechInterim(interim);
    };
    recognition.onerror = (e: any) => {
      if (e.error === 'not-allowed') {
        setSpeechSupported(false);
      }
    };
    recognition.onend = () => {
      // 録音中なら自動再起動
      if (mediaRecorderRef.current?.state === 'recording') {
        try { recognition.start(); } catch {}
      }
    };
    recognitionRef.current = recognition;
    recognition.start();
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    setSpeechFinal('');
    setSpeechInterim('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.start(1000); // 1秒ごとにチャンク収集
      mediaRecorderRef.current = recorder;

      setRecording(true);
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed(prev => prev + 1), 1000);

      // Web Speech API 起動
      if (speechSupported) startSpeechRecognition();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'マイクにアクセスできません');
    }
  }, [speechSupported, startSpeechRecognition]);

  const stopRecording = useCallback(async () => {
    // 録音停止 — stop() は非同期なので最終チャンクを待つ
    const recorder = mediaRecorderRef.current;
    const blob = await new Promise<Blob>((resolve) => {
      if (!recorder || recorder.state === 'inactive') {
        resolve(new Blob(chunksRef.current, { type: 'audio/webm' }));
        return;
      }
      recorder.onstop = () => {
        resolve(new Blob(chunksRef.current, { type: 'audio/webm' }));
      };
      recorder.stop();
    });
    streamRef.current?.getTracks().forEach(t => t.stop());
    if (timerRef.current) clearInterval(timerRef.current);
    recognitionRef.current?.stop();
    setRecording(false);
    if (blob.size === 0) {
      setError('録音データが空です');
      return;
    }

    setUploading(true);
    try {
      const now = new Date();
      const filename = `録音_${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}.webm`;

      const formData = new FormData();
      formData.append('file', blob, filename);
      const res = await authFetch('/api/meetings/transcribe', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Upload failed');
      }
      const data = await res.json();
      onUploaded(data.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'アップロードに失敗しました');
    } finally {
      setUploading(false);
    }
  }, [onUploaded]);

  // クリーンアップ
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach(t => t.stop());
      if (timerRef.current) clearInterval(timerRef.current);
      recognitionRef.current?.stop();
    };
  }, []);

  if (uploading) {
    return (
      <div className="border-2 border-dashed border-indigo-300 rounded-xl p-8 text-center">
        <Loader2 className="w-10 h-10 text-indigo-500 animate-spin mx-auto mb-3" />
        <p className="text-sm text-indigo-600 font-medium">録音データをアップロード中...</p>
        <p className="text-xs text-gray-500 mt-1">バックグラウンドで文字起こし・議事録生成が始まります</p>
      </div>
    );
  }

  if (recording) {
    return (
      <div className="border-2 border-red-200 rounded-xl p-6 space-y-4">
        {/* 録音ステータス */}
        <div className="flex items-center justify-between">
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

        {/* Web Speech API リアルタイム表示 */}
        {speechSupported && (
          <div className="bg-gray-50 rounded-lg p-4 max-h-40 overflow-y-auto">
            <p className="text-xs font-medium text-gray-500 mb-2">リアルタイム文字起こし（速報）</p>
            {(speechFinal || speechInterim) ? (
              <div className="text-sm leading-relaxed">
                <span className="text-gray-800">{speechFinal}</span>
                {speechInterim && <span className="text-gray-400 italic">{speechInterim}</span>}
              </div>
            ) : (
              <p className="text-sm text-gray-400">話し始めると文字起こしが表示されます...</p>
            )}
          </div>
        )}
        {speechSupported === false && (
          <p className="text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
            Web Speech APIは非対応です。録音停止後にGeminiで高精度文字起こしを行います。
          </p>
        )}

        <button
          onClick={stopRecording}
          className="w-full py-3 rounded-xl bg-gray-800 text-white text-sm font-semibold hover:bg-gray-900 transition-colors flex items-center justify-center gap-2"
        >
          <Square className="w-4 h-4 fill-white" />
          録音を停止して議事録を生成
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <button
        onClick={startRecording}
        className="w-full flex items-center justify-center gap-2 py-4 rounded-xl border-2 border-dashed border-red-300 text-red-500 hover:bg-red-50 hover:border-red-400 transition-all font-medium"
      >
        <Mic className="w-5 h-5" />
        録音開始
      </button>
      {error && (
        <div className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
          {error}
        </div>
      )}
    </div>
  );
}
