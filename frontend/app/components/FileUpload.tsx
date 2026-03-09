"use client";

import { useState, useCallback, useEffect, useRef } from 'react';
import { authFetch } from '@/lib/api';
import { useDropzone } from 'react-dropzone';

interface OcrJob {
    file_path: string;
    filename: string;
    status: 'processing' | 'completed' | 'failed' | 'dismissed' | string;
    processed_pages: number;
    total_pages: number;
    error_message?: string;
    estimated_remaining?: number;
    updated_at?: string;
}

/** ステータスに対応するラベル・色・アイコン */
const STATUS_CONFIG: Record<string, { label: string; icon: string; bar: string; bg: string; text: string; border: string }> = {
    processing:          { label: 'OCR処理中',       icon: '⏳', bar: 'bg-blue-500',   bg: 'bg-blue-50 dark:bg-blue-900/20',   text: 'text-blue-700 dark:text-blue-300',  border: 'border-blue-200 dark:border-blue-800' },
    ocr_completed:       { label: 'OCR完了・分類中',  icon: '🔍', bar: 'bg-indigo-500', bg: 'bg-indigo-50 dark:bg-indigo-900/20',text: 'text-indigo-700 dark:text-indigo-300',border:'border-indigo-200 dark:border-indigo-800'},
    uploading_to_drive:  { label: 'Drive同期中',      icon: '☁️', bar: 'bg-cyan-500',   bg: 'bg-cyan-50 dark:bg-cyan-900/20',   text: 'text-cyan-700 dark:text-cyan-300',  border: 'border-cyan-200 dark:border-cyan-800' },
    drive_synced:        { label: 'Drive同期済み',    icon: '✅', bar: 'bg-teal-500',   bg: 'bg-teal-50 dark:bg-teal-900/20',   text: 'text-teal-700 dark:text-teal-300',  border: 'border-teal-200 dark:border-teal-800' },
    enriched:            { label: 'メタデータ付与済',  icon: '🏷️', bar: 'bg-violet-500', bg: 'bg-violet-50 dark:bg-violet-900/20',text:'text-violet-700 dark:text-violet-300',border:'border-violet-200 dark:border-violet-800'},
    indexing:            { label: 'インデックス中',    icon: '📦', bar: 'bg-amber-500',  bg: 'bg-amber-50 dark:bg-amber-900/20', text: 'text-amber-700 dark:text-amber-300', border: 'border-amber-200 dark:border-amber-800'},
    completed:           { label: 'RAG登録完了',      icon: '✅', bar: 'bg-green-500',  bg: 'bg-green-50 dark:bg-green-900/20', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800'},
    failed:              { label: 'エラー',            icon: '❌', bar: 'bg-red-500',    bg: 'bg-red-50 dark:bg-red-900/20',     text: 'text-red-700 dark:text-red-300',    border: 'border-red-200 dark:border-red-800'   },
    enrichment_failed:   { label: '分類エラー',        icon: '⚠️', bar: 'bg-orange-500', bg: 'bg-orange-50 dark:bg-orange-900/20',text:'text-orange-700 dark:text-orange-300',border:'border-orange-200 dark:border-orange-800'},
};

const PIPELINE_STAGES = ['processing', 'ocr_completed', 'enriched', 'indexing', 'completed'];

/** パイプラインの進行度 (0–100) */
function pipelineProgress(status: string, processedPages: number, totalPages: number): number {
    const stageIdx = PIPELINE_STAGES.indexOf(status);
    if (status === 'completed') return 100;
    if (status === 'failed' || status === 'enrichment_failed') return 0;
    if (status === 'processing') {
        // OCR ページ進捗
        if (totalPages > 0) return Math.min(30, Math.round((processedPages / totalPages) * 30));
        return 5;
    }
    if (stageIdx >= 0) return 30 + stageIdx * 18;
    return 10;
}

const SpinnerIcon = () => (
    <span className="inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin shrink-0" />
);

function OcrJobCard({
    job,
    onDismiss,
    dismissing,
}: {
    job: OcrJob;
    onDismiss: (path: string) => void;
    dismissing: boolean;
}) {
    const cfg = STATUS_CONFIG[job.status] ?? STATUS_CONFIG['processing'];
    const isActive = job.status === 'processing' || job.status === 'indexing' || job.status === 'uploading_to_drive';
    const isDone   = job.status === 'completed';
    const isError  = job.status === 'failed' || job.status === 'enrichment_failed';
    const progress = pipelineProgress(job.status, job.processed_pages, job.total_pages);

    return (
        <div className={`rounded-lg border px-3 py-2 text-[11px] flex flex-col gap-1.5 ${cfg.bg} ${cfg.border}`}>
            {/* ヘッダー行 */}
            <div className="flex items-center gap-1.5 min-w-0">
                {isActive ? <SpinnerIcon /> : <span className="shrink-0">{cfg.icon}</span>}
                <span className={`font-medium truncate flex-1 min-w-0 ${cfg.text}`}>
                    {job.filename}
                </span>
                <span className={`shrink-0 font-semibold text-[10px] px-1.5 py-0.5 rounded border ${cfg.bg} ${cfg.text} ${cfg.border}`}>
                    {cfg.label}
                </span>
                {!isActive && (
                    <button
                        onClick={() => onDismiss(job.file_path)}
                        disabled={dismissing}
                        className="shrink-0 ml-1 text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 leading-none transition-colors"
                        title="閉じる"
                        aria-label="閉じる"
                    >
                        ×
                    </button>
                )}
            </div>

            {/* プログレスバー */}
            {!isError && (
                <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
                    <div
                        className={`h-full rounded-full transition-all duration-700 ${cfg.bar} ${isActive ? 'animate-pulse' : ''}`}
                        style={{ width: `${progress}%` }}
                    />
                </div>
            )}

            {/* OCR ページ進捗（processing 中のみ） */}
            {job.status === 'processing' && job.total_pages > 0 && (
                <div className="flex items-center justify-between text-[10px] text-slate-500 dark:text-slate-400">
                    <span>ページ: {job.processed_pages} / {job.total_pages}</span>
                    {job.estimated_remaining != null && job.estimated_remaining > 0 && (
                        <span>残り約 {Math.ceil(job.estimated_remaining)}秒</span>
                    )}
                </div>
            )}

            {/* パイプラインステップインジケーター */}
            {!isError && (
                <div className="flex items-center gap-1 mt-0.5">
                    {['OCR', '分類', 'インデックス', '完了'].map((label, i) => {
                        const stepStatuses = [
                            ['processing'],
                            ['ocr_completed', 'enriched', 'uploading_to_drive', 'drive_synced'],
                            ['indexing'],
                            ['completed'],
                        ];
                        const stageIdx = PIPELINE_STAGES.indexOf(job.status);
                        const done = stageIdx > i || isDone;
                        const active = stepStatuses[i]?.includes(job.status);
                        return (
                            <div key={i} className="flex items-center gap-1">
                                <div className={`w-4 h-4 rounded-full flex items-center justify-center text-[8px] font-bold shrink-0 border transition-all ${
                                    done    ? 'bg-green-500 border-green-500 text-white' :
                                    active  ? `${cfg.bar} border-transparent text-white` :
                                              'bg-slate-200 dark:bg-slate-700 border-slate-300 dark:border-slate-600 text-slate-400'
                                }`}>
                                    {done ? '✓' : i + 1}
                                </div>
                                <span className={`text-[9px] ${done || active ? cfg.text : 'text-slate-400 dark:text-slate-500'}`}>
                                    {label}
                                </span>
                                {i < 3 && <span className="text-slate-300 dark:text-slate-600">›</span>}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* エラーメッセージ */}
            {isError && job.error_message && (
                <div className="mt-0.5 p-1.5 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded text-[10px] text-red-700 dark:text-red-300 break-all max-h-16 overflow-y-auto">
                    <span className="font-bold">エラー詳細: </span>{job.error_message}
                </div>
            )}
        </div>
    );
}

const FileUpload = () => {
    const [uploading, setUploading] = useState(false);
    const [uploadMsg, setUploadMsg] = useState<string | null>(null);
    const [uploadStatus, setUploadStatus] = useState<'success' | 'error' | null>(null);
    const [jobs, setJobs] = useState<OcrJob[]>([]);
    const [processingCount, setProcessingCount] = useState(0);
    const [dismissing, setDismissing] = useState<Set<string>>(new Set());
    const pollRef = useRef<NodeJS.Timeout | null>(null);

    const fetchOcrStatus = useCallback(async () => {
        try {
            const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
            const res = await authFetch(`${API_BASE}/api/ocr/status`);
            if (!res.ok) return;
            const data = await res.json();
            setJobs(data.jobs || []);
            setProcessingCount(data.processing_count || 0);
        } catch (_) { }
    }, []);

    // 初回ロード
    useEffect(() => {
        fetchOcrStatus();
    }, [fetchOcrStatus]);

    // processing ジョブがある間だけポーリング（3秒）
    useEffect(() => {
        if (processingCount > 0) {
            pollRef.current = setInterval(fetchOcrStatus, 3000);
        } else {
            if (pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
            }
        }
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [processingCount, fetchOcrStatus]);

    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        if (acceptedFiles.length === 0) return;

        setUploading(true);
        setUploadMsg(acceptedFiles.length === 1
            ? `アップロード中: ${acceptedFiles[0].name}...`
            : `${acceptedFiles.length}件のファイルをアップロード中...`);
        setUploadStatus(null);

        const formData = new FormData();
        acceptedFiles.forEach(file => formData.append('files', file));

        try {
            const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
            const res = await authFetch(`${API_BASE}/api/upload/multiple`, {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(err.detail || 'Upload failed');
            }

            const data = await res.json();
            setUploadStatus('success');
            const totalUploaded = data.uploaded?.length || 0;
            const totalErrors = data.errors?.length || 0;
            setUploadMsg(
                `${totalUploaded}件アップロード完了。OCR処理を開始しました。` +
                (totalErrors > 0 ? ` (${totalErrors}件失敗)` : '')
            );

            // すぐにジョブ一覧を更新してポーリング開始
            setTimeout(fetchOcrStatus, 1500);
        } catch (error: any) {
            setUploadStatus('error');
            setUploadMsg(`アップロード失敗: ${error.message}`);
        } finally {
            setUploading(false);
        }
    }, [fetchOcrStatus]);

    const dismissJob = useCallback(async (filePath: string) => {
        setDismissing(prev => new Set(prev).add(filePath));
        try {
            const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
            await authFetch(`${API_BASE}/api/ocr/status/${encodeURIComponent(filePath)}`, { method: 'DELETE' });
        } catch (_) { }
        // エラーでも UI から削除
        setJobs(prev => prev.filter(j => j.file_path !== filePath));
        setDismissing(prev => { const s = new Set(prev); s.delete(filePath); return s; });
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: {
            'application/pdf': ['.pdf'],
            'image/png': ['.png'],
            'image/jpeg': ['.jpg', '.jpeg'],
        },
        multiple: true,
    });

    const activeJobs  = jobs.filter(j => j.status !== 'completed' && j.status !== 'failed' && j.status !== 'enrichment_failed');
    const doneJobs    = jobs.filter(j => j.status === 'completed');
    const errorJobs   = jobs.filter(j => j.status === 'failed' || j.status === 'enrichment_failed');

    return (
        <div className="p-4 bg-white dark:bg-slate-900 rounded-lg shadow mb-4">
            <h2 className="text-base font-bold mb-3 text-gray-800 dark:text-slate-100">ファイルアップロード</h2>

            {/* ドロップゾーン */}
            <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                    isDragActive
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                        : 'border-gray-300 dark:border-slate-600 hover:border-blue-400 dark:hover:border-blue-500'
                }`}
            >
                <input {...getInputProps()} />
                {uploading ? (
                    <div className="flex flex-col items-center gap-2">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
                        <p className="text-sm text-gray-600 dark:text-slate-300">アップロード中...</p>
                    </div>
                ) : (
                    <div>
                        <p className="text-sm text-gray-600 dark:text-slate-300 mb-1">
                            ここにファイルをドラッグ＆ドロップ
                        </p>
                        <p className="text-xs text-gray-400 dark:text-slate-500">
                            クリックして選択 (.pdf, .png, .jpg)
                        </p>
                    </div>
                )}
            </div>

            {/* アップロード結果メッセージ */}
            {uploadMsg && (
                <div className={`mt-2 px-3 py-2 rounded text-xs ${
                    uploadStatus === 'success'  ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                    uploadStatus === 'error'    ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                                  'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                }`}>
                    {uploadMsg}
                </div>
            )}

            {/* OCR 処理状況パネル */}
            {jobs.length > 0 && (
                <div className="mt-3">
                    {/* ヘッダー */}
                    <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">📊 処理状況</span>
                        {processingCount > 0 && (
                            <span className="text-[10px] bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full font-medium animate-pulse">
                                {processingCount}件処理中
                            </span>
                        )}
                        {errorJobs.length > 0 && (
                            <span className="text-[10px] bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 px-2 py-0.5 rounded-full font-medium">
                                {errorJobs.length}件エラー
                            </span>
                        )}
                        {doneJobs.length > 0 && (
                            <span className="text-[10px] bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 px-2 py-0.5 rounded-full font-medium">
                                {doneJobs.length}件完了
                            </span>
                        )}
                        <button
                            onClick={fetchOcrStatus}
                            className="ml-auto text-[10px] text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 transition-colors"
                            title="更新"
                        >
                            🔄
                        </button>
                    </div>

                    <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
                        {/* エラーを先頭に表示 */}
                        {errorJobs.map(job => (
                            <OcrJobCard
                                key={job.file_path}
                                job={job}
                                onDismiss={dismissJob}
                                dismissing={dismissing.has(job.file_path)}
                            />
                        ))}
                        {/* 処理中 */}
                        {activeJobs.map(job => (
                            <OcrJobCard
                                key={job.file_path}
                                job={job}
                                onDismiss={dismissJob}
                                dismissing={dismissing.has(job.file_path)}
                            />
                        ))}
                        {/* 完了 */}
                        {doneJobs.map(job => (
                            <OcrJobCard
                                key={job.file_path}
                                job={job}
                                onDismiss={dismissJob}
                                dismissing={dismissing.has(job.file_path)}
                            />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default FileUpload;
