"use client";

import { useState, useCallback, useEffect, useRef } from 'react';
import { authFetch } from '@/lib/api';
import { useDropzone } from 'react-dropzone';

interface OcrJob {
    file_path: string;
    filename: string;
    status: 'processing' | 'completed' | 'failed';
    processed_pages: number;
    total_pages: number;
    error_message?: string;
    estimated_remaining?: number;
}

const StatusIcon = ({ status }: { status: string }) => {
    if (status === 'processing') return (
        <span className="inline-block w-3 h-3 rounded-full border-2 border-blue-400 border-t-transparent animate-spin mr-1.5 flex-shrink-0" />
    );
    if (status === 'completed') return <span className="text-green-500 mr-1.5">✓</span>;
    if (status === 'failed') return <span className="text-red-500 mr-1.5">✕</span>;
    return null;
};

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

    // Poll while any job is processing
    useEffect(() => {
        fetchOcrStatus();
        pollRef.current = setInterval(fetchOcrStatus, 3000);
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [fetchOcrStatus]);

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
                const err = await res.json();
                throw new Error(err.detail || 'Upload failed');
            }

            const data = await res.json();
            setUploadStatus('success');
            const totalUploaded = data.uploaded?.length || 0;
            const totalErrors = data.errors?.length || 0;
            setUploadMsg(`${totalUploaded}件アップロード完了。OCR処理を開始しました。` + (totalErrors > 0 ? ` (${totalErrors}件失敗)` : ''));

            // Immediately refresh job status
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
            setJobs(prev => prev.filter(j => j.file_path !== filePath));
        } catch (_) {
            // サイレントに失敗してもUIから消す
            setJobs(prev => prev.filter(j => j.file_path !== filePath));
        } finally {
            setDismissing(prev => { const s = new Set(prev); s.delete(filePath); return s; });
        }
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

    return (
        <div className="p-4 bg-white dark:bg-slate-900 rounded-lg shadow mb-4">
            <h2 className="text-base font-bold mb-3 text-gray-800 dark:text-slate-100">ファイルアップロード</h2>

            <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${isDragActive ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
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
                            または、クリックしてファイルを選択 (.pdf, .png, .jpg)
                        </p>
                    </div>
                )}
            </div>

            {uploadMsg && (
                <div className={`mt-2 px-3 py-2 rounded text-xs ${uploadStatus === 'success' ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                        : uploadStatus === 'error' ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                            : 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                    }`}>
                    {uploadMsg}
                </div>
            )}

            {/* OCR Job Progress Panel */}
            {jobs.length > 0 && (
                <div className="mt-3">
                    <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">処理状況</span>
                        {processingCount > 0 && (
                            <span className="text-[10px] bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full font-medium animate-pulse">
                                {processingCount}件処理中
                            </span>
                        )}
                    </div>
                    <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                        {jobs.map((job) => (
                            <div
                                key={job.file_path}
                                className={`rounded p-2 text-[11px] flex flex-col gap-1 ${job.status === 'processing' ? 'bg-blue-50 dark:bg-blue-900/20'
                                        : job.status === 'completed' ? 'bg-green-50 dark:bg-green-900/20'
                                            : 'bg-red-50 dark:bg-red-900/20'
                                    }`}
                            >
                                <div className="flex items-center">
                                    <StatusIcon status={job.status} />
                                    <span className="font-medium truncate text-slate-700 dark:text-slate-200 flex-1 min-w-0">
                                        {job.filename}
                                    </span>
                                    <span className={`ml-2 flex-shrink-0 ${job.status === 'processing' ? 'text-blue-600 dark:text-blue-400'
                                            : job.status === 'completed' ? 'text-green-600 dark:text-green-400'
                                                : 'text-red-600 dark:text-red-400'
                                        }`}>
                                        {job.status === 'processing' ? `${job.processed_pages}/${job.total_pages}ページ`
                                            : job.status === 'completed' ? 'OCR完了'
                                                : 'エラー'}
                                    </span>
                                    {job.status !== 'processing' && (
                                        <button
                                            onClick={() => dismissJob(job.file_path)}
                                            disabled={dismissing.has(job.file_path)}
                                            className="ml-2 flex-shrink-0 text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 leading-none"
                                            title="閉じる"
                                        >
                                            ×
                                        </button>
                                    )}
                                </div>
                                {job.status === 'processing' && (
                                    <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-1">
                                        <div
                                            className="bg-blue-500 h-1 rounded-full transition-all duration-500"
                                            style={{ width: `${Math.min(100, (job.processed_pages / Math.max(1, job.total_pages)) * 100)}%` }}
                                        />
                                    </div>
                                )}
                                {job.status === 'processing' && job.estimated_remaining && (
                                    <span className="text-blue-500 dark:text-blue-400 text-[10px]">
                                        残り約 {Math.ceil(job.estimated_remaining)}秒
                                    </span>
                                )}
                                {job.status === 'failed' && job.error_message && (
                                    <span className="text-red-500 text-[10px] break-all">{job.error_message}</span>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default FileUpload;
