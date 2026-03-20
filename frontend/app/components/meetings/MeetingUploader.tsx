'use client';

import { useCallback, useState, useRef } from 'react';
import { Upload, FileAudio, Loader2, CheckCircle } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface Props {
  onUploaded: (id: string) => void;
}

const ACCEPT = '.webm,.mp3,.wav,.m4a,.mp4,.ogg';

export default function MeetingUploader({ onUploaded }: Props) {
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [uploadedName, setUploadedName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadFile = useCallback(async (file: File) => {
    setUploading(true);
    setUploadedName(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await authFetch('/api/meetings/transcribe', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Upload failed');
      }
      const data = await res.json();
      setUploadedName(file.name);
      onUploaded(data.id);
      // 3秒後に成功表示をリセット
      setTimeout(() => setUploadedName(null), 3000);
    } catch (e) {
      alert(`アップロードエラー: ${e instanceof Error ? e.message : e}`);
    } finally {
      setUploading(false);
    }
  }, [onUploaded]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
    if (inputRef.current) inputRef.current.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  };

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => !uploading && inputRef.current?.click()}
      className={`
        relative border-2 border-dashed rounded-xl p-4 md:p-8 text-center cursor-pointer transition-all
        ${dragOver
          ? 'border-indigo-400 bg-indigo-50'
          : uploading
            ? 'border-gray-300 bg-gray-50 cursor-wait'
            : 'border-gray-300 hover:border-indigo-400 hover:bg-indigo-50/50'
        }
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        onChange={handleFileChange}
        className="hidden"
      />

      {uploading ? (
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-10 h-10 text-indigo-500 animate-spin" />
          <p className="text-sm text-indigo-600 font-medium">アップロード中...</p>
        </div>
      ) : uploadedName ? (
        <div className="flex flex-col items-center gap-3">
          <CheckCircle className="w-10 h-10 text-green-500" />
          <p className="text-sm text-green-600 font-medium">{uploadedName} をアップロードしました</p>
          <p className="text-xs text-gray-500">バックグラウンドで文字起こし・議事録生成を実行中...</p>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <div className="w-14 h-14 rounded-full bg-indigo-100 flex items-center justify-center">
            <FileAudio className="w-7 h-7 text-indigo-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700">
              <span className="hidden md:inline">音声ファイルをドラッグ&ドロップ</span>
              <span className="md:hidden">タップして音声ファイルを選択</span>
            </p>
            <p className="text-xs text-gray-500 mt-1">
              <span className="hidden md:inline">または クリックしてファイルを選択</span>
              webm, mp3, wav, m4a対応
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
