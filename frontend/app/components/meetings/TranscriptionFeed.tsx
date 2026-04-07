'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Mic, MicOff } from 'lucide-react';

interface Props {
  speechFinal: string;
  speechInterim: string;
  speechSupported: boolean | null;
  speechError: string | null;
  transcripts: string[];
  sendingChunk: boolean;
  chunkIndex: number;
  /** 録音中かどうか（録音中はGemini表示を非表示にする） */
  isRecording?: boolean;
}

export default function TranscriptionFeed({
  speechFinal,
  speechInterim,
  speechSupported,
  speechError,
  transcripts,
  sendingChunk,
  chunkIndex,
  isRecording = false,
}: Props) {
  const [userScrolled, setUserScrolled] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // 自動スクロール
  useEffect(() => {
    if (!userScrolled && endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [speechFinal, speechInterim, transcripts, userScrolled]);

  const handleScroll = useCallback(() => {
    if (!feedRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = feedRef.current;
    setUserScrolled(scrollHeight - scrollTop - clientHeight > 40);
  }, []);

  return (
    <div className="bg-white rounded-2xl border border-gray-200 flex flex-col h-full">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 flex-shrink-0">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          文字起こし
          {(speechFinal || speechInterim) && (
            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
          )}
        </h3>
        {!isRecording && (
          <div className="flex items-center gap-2 text-xs text-gray-400">
            {sendingChunk && (
              <span className="flex items-center gap-1 text-blue-500">
                <Loader2 className="w-3 h-3 animate-spin" />処理中...
              </span>
            )}
            {chunkIndex > 0 && !sendingChunk && (
              <span className="text-green-600">{chunkIndex} 件完了</span>
            )}
          </div>
        )}
      </div>

      {/* フィード本体 */}
      <div
        ref={feedRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-5 space-y-4"
      >
        {/* Web Speech リアルタイム */}
        <div>
          <p className="text-xs font-medium text-gray-400 mb-2 flex items-center gap-1.5">
            {speechSupported === false ? (
              <MicOff className="w-3 h-3" />
            ) : (
              <Mic className="w-3 h-3" />
            )}
            リアルタイム文字起こし
          </p>
          {speechSupported === false ? (
            <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
              Web Speech APIは非対応です。録音停止後にGeminiで高精度文字起こしを行います。
            </p>
          ) : speechError ? (
            <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
              {speechError}
            </p>
          ) : (speechFinal || speechInterim) ? (
            <div className="text-sm leading-relaxed bg-gray-50 rounded-lg p-3">
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
                  <span
                    key={i}
                    className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Gemini 高精度文字起こし（録音停止後のみ表示） */}
        {!isRecording && transcripts.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-400 mb-2">
              Gemini 高精度文字起こし
            </p>
            <div className="space-y-3">
              {transcripts.map((text, i) => (
                <div key={i} className="border-l-2 border-blue-200 pl-3">
                  <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
}
