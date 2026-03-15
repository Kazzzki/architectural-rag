'use client';

import React, { useCallback, useRef, useState } from 'react';
import { Mic } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface CaptureTextInputProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  projectName: string;
  onProjectChange: (v: string) => void;
  projects: string[];
}

export default function CaptureTextInput({ value, onChange, onSubmit, submitting, projectName, onProjectChange, projects }: CaptureTextInputProps) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        await transcribeBlob(blob);
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
    } catch {
      // MediaRecorder 非対応: SpeechRecognition にフォールバック
      fallbackSpeechRecognition();
    }
  }, []);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setRecording(false);
  }, []);

  async function transcribeBlob(blob: Blob) {
    setTranscribing(true);
    try {
      const fd = new FormData();
      fd.append('file', blob, 'voice.webm');
      const res = await authFetch('/api/transcribe', { method: 'POST', body: fd });
      if (res.ok) {
        const data = await res.json();
        const transcribed = data.text ?? data.transcript ?? '';
        if (transcribed) onChange(value ? `${value}\n${transcribed}` : transcribed);
      }
    } catch {
      // 無視
    } finally {
      setTranscribing(false);
    }
  }

  function fallbackSpeechRecognition() {
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.lang = 'ja-JP';
    rec.interimResults = false;
    rec.onresult = (e: any) => {
      const text = e.results[0]?.[0]?.transcript ?? '';
      if (text) onChange(value ? `${value}\n${text}` : text);
    };
    rec.onend = () => setRecording(false);
    rec.start();
    setRecording(true);
  }

  const handlePTTDown = (e: React.TouchEvent | React.MouseEvent) => {
    e.preventDefault();
    startRecording();
  };

  const handlePTTUp = (e: React.TouchEvent | React.MouseEvent) => {
    e.preventDefault();
    if (recording) stopRecording();
  };

  return (
    <div className="space-y-3">
      {/* テキストエリア */}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="課題を自由に入力してください…"
        disabled={submitting}
        style={{ fontSize: 16, minHeight: 100 }}
        className="w-full resize-none border border-gray-300 rounded-xl p-3 focus:outline-none focus:ring-2 focus:ring-blue-400 text-gray-800"
      />

      {/* 音声ボタン */}
      <button
        onTouchStart={handlePTTDown}
        onTouchEnd={handlePTTUp}
        onMouseDown={handlePTTDown}
        onMouseUp={handlePTTUp}
        disabled={transcribing || submitting}
        style={{ height: 56, fontSize: 16 }}
        className={`w-full flex items-center justify-center gap-2 rounded-xl font-medium border transition-all select-none
          ${recording
            ? 'bg-red-500 text-white border-red-500 animate-pulse'
            : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
          }
          ${(transcribing || submitting) ? 'opacity-50 cursor-not-allowed' : ''}
        `}
      >
        <Mic size={20} />
        {transcribing ? '転写中…' : recording ? '話してください（離して終了）' : '押して話す'}
      </button>

      {/* プロジェクト選択 */}
      <div className="flex items-center gap-2">
        <label className="text-sm text-gray-500 flex-shrink-0">プロジェクト</label>
        <input
          list="capture-project-list"
          value={projectName}
          onChange={(e) => onProjectChange(e.target.value)}
          placeholder="プロジェクト名を入力または選択…"
          disabled={submitting}
          style={{ fontSize: 16 }}
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <datalist id="capture-project-list">
          {projects.map((p) => (
            <option key={p} value={p} />
          ))}
        </datalist>
      </div>

      {/* 送信ボタン */}
      <button
        onClick={onSubmit}
        disabled={submitting || !value.trim() || !projectName.trim()}
        style={{ height: 56, fontSize: 16 }}
        className="w-full bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors active:scale-95"
      >
        {submitting ? '処理中…' : '送信して整理する'}
      </button>
    </div>
  );
}
