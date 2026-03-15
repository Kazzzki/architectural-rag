import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { 
    FileText, 
    File, 
    Folder, 
    Trash2, 
    Download, 
    RefreshCw, 
    ChevronRight, 
    ChevronDown, 
    Library as LibraryIcon,
    X,
    Eye
} from 'lucide-react';
import { authFetch } from '@/lib/api';
import { OcrJob, OcrJobCard } from './FileUpload';
import ReactMarkdown from 'react-markdown';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// --- Types ---
interface Stats {
    file_count: number;
    chunk_count: number;
    last_updated: string;
}

interface FileNode {
    name: string;
    type: 'directory' | 'file';
    path: string;
    children?: FileNode[];
    size?: number;
    ocr_status?: 'completed' | 'none' | 'processing' | 'failed';
    ocr_progress?: {
        current: number;
        total: number;
        estimated_remaining?: number;
        error?: string;
    };
}

// --- Helper Functions ---
const formatSize = (bytes?: number) => {
    if (bytes === undefined) return '-';
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const formatDate = (iso: string) => {
    if (!iso) return '-';
    // Simplified relative time format
    const diffMs = Date.now() - new Date(iso).getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'たった今';
    if (diffMins < 60) return `${diffMins}分前`;
    const diffHrs = Math.floor(diffMins / 60);
    if (diffHrs < 24) return `${diffHrs}時間前`;
    const diffDays = Math.floor(diffHrs / 24);
    return `${diffDays}日前`;
};

// --- Library Panel Component ---
export default function LibraryPanel() {
    // Stats State
    const [stats, setStats] = useState<Stats | null>(null);
    
    // OCR Jobs State
    const [jobs, setJobs] = useState<OcrJob[]>([]);
    const [processingCount, setProcessingCount] = useState(0);
    const [dismissing, setDismissing] = useState<Set<string>>(new Set());
    const pollRef = useRef<NodeJS.Timeout | null>(null);

    // Upload State
    const [uploading, setUploading] = useState(false);
    
    // File List State
    const [tree, setTree] = useState<FileNode | null>(null);
    const [treeLoading, setTreeLoading] = useState(false);
    const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
    const [isDeleting, setIsDeleting] = useState(false);

    // Modal State
    const [detailFile, setDetailFile] = useState<FileNode | null>(null);

    // --- Data Fetching ---
    
    const fetchStats = async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/stats`);
            if (res.ok) setStats(await res.json());
        } catch (_) {}
    };

    const fetchOcrStatus = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/ocr/status`);
            if (!res.ok) return;
            const data = await res.json();
            setJobs(data.jobs || []);
            setProcessingCount(data.processing_count || 0);
        } catch (_) {}
    }, []);

    const fetchTree = useCallback(async () => {
        setTreeLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/files/tree`);
            if (res.ok) setTree(await res.json());
        } catch (_) {
        } finally {
            setTreeLoading(false);
        }
    }, []);

    // Initial load
    useEffect(() => {
        fetchStats();
        fetchOcrStatus();
        fetchTree();
        
        const statsInterval = setInterval(fetchStats, 30000);
        return () => clearInterval(statsInterval);
    }, [fetchOcrStatus, fetchTree]);

    // Polling for OCR jobs
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

    // --- Upload Logic ---
    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        if (acceptedFiles.length === 0) return;

        setUploading(true);
        const formData = new FormData();
        acceptedFiles.forEach(file => formData.append('files', file));

        try {
            const res = await authFetch(`${API_BASE}/api/upload/multiple`, {
                method: 'POST',
                body: formData,
            });

            if (res.ok) {
                setTimeout(fetchOcrStatus, 1500);
                setTimeout(fetchTree, 2000);
                setTimeout(fetchStats, 3000);
            }
        } catch (error) {
            console.error('Upload Error', error);
        } finally {
            setUploading(false);
        }
    }, [fetchOcrStatus, fetchTree]);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: {
            'application/pdf': ['.pdf'],
            'image/png': ['.png'],
            'image/jpeg': ['.jpg', '.jpeg'],
        },
        multiple: true,
    });

    const dismissJob = useCallback(async (filePath: string) => {
        setDismissing(prev => new Set(prev).add(filePath));
        try {
            await authFetch(`${API_BASE}/api/ocr/status/${encodeURIComponent(filePath)}`, { method: 'DELETE' });
        } catch (_) { }
        setJobs(prev => prev.filter(j => j.file_path !== filePath));
        setDismissing(prev => { const s = new Set(prev); s.delete(filePath); return s; });
    }, []);

    // --- File List Logic ---
    // Flatten tree structure
    const getFlattenedFiles = (node: FileNode | null): FileNode[] => {
        if (!node) return [];
        let files: FileNode[] = [];
        if (node.type === 'file') {
            files.push(node);
        }
        if (node.children) {
            node.children.forEach(child => {
                files = files.concat(getFlattenedFiles(child));
            });
        }
        return files;
    };

    const flatFiles = getFlattenedFiles(tree);

    const handleCheckToggle = (path: string, checked: boolean) => {
        setSelectedPaths(prev => {
            const next = new Set(prev);
            checked ? next.add(path) : next.delete(path);
            return next;
        });
    };

    const confirmBulkDelete = async () => {
        if (selectedPaths.size === 0) return;
        if (!window.confirm(`選択した ${selectedPaths.size} 件のファイルを削除しますか？`)) return;

        setIsDeleting(true);
        try {
            const res = await authFetch(`${API_BASE}/api/files/bulk-delete`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_paths: Array.from(selectedPaths) })
            });

            if (res.ok) {
                const data = await res.json();
                setSelectedPaths(new Set());
                fetchTree();
                fetchStats();
                if (data.errors && data.errors.length > 0) {
                    alert(`一部のファイルの削除に失敗しました:\n${data.errors.join('\n')}`);
                }
            } else {
                const data = await res.json().catch(() => ({}));
                alert(`削除に失敗しました: ${data.detail || res.statusText}`);
            }
        } catch (error) {
            console.error('Bulk delete error:', error);
            alert('削除中にエラーが発生しました');
        } finally {
            setIsDeleting(false);
        }
    };

    const activeJobs = jobs.filter(j => j.status !== 'completed' && j.status !== 'failed' && j.status !== 'enrichment_failed');
    
    // Check if we should render Jobs section
    const shouldShowJobs = jobs.length > 0;

    return (
        <div className="flex flex-col h-full bg-[var(--background)] text-[var(--foreground)] relative">
            
            {/* [A] Stats Header */}
            <div className="flex shrink-0 border-b border-[var(--border)] bg-white divide-x divide-[var(--border)]">
                <div className="flex-1 py-3 flex flex-col items-center justify-center">
                    <span className="text-sm font-bold text-blue-600 mb-0.5 whitespace-nowrap">📄 {stats?.file_count || 0}</span>
                    <span className="text-[10px] text-[var(--muted)] whitespace-nowrap">ファイル</span>
                </div>
                <div className="flex-1 py-3 flex flex-col items-center justify-center">
                    <span className="text-sm font-bold text-violet-600 mb-0.5 whitespace-nowrap">🔷 {(stats?.chunk_count || 0).toLocaleString()}</span>
                    <span className="text-[10px] text-[var(--muted)] whitespace-nowrap">チャンク</span>
                </div>
                <div className="flex-1 py-3 flex flex-col items-center justify-center">
                    <span className="text-sm font-bold text-slate-600 mb-0.5 whitespace-nowrap">🕐 {formatDate(stats?.last_updated || '')}</span>
                    <span className="text-[10px] text-[var(--muted)] whitespace-nowrap">更新</span>
                </div>
                {processingCount > 0 && (
                    <div className="py-2 px-3 bg-blue-50/50 flex flex-col items-center justify-center text-blue-700 animate-pulse transition-all">
                        <RefreshCw className="w-4 h-4 mb-1" />
                        <span className="text-[10px] font-bold whitespace-nowrap">{processingCount}件処理中</span>
                    </div>
                )}
            </div>

            {/* [B] Active Jobs */}
            {shouldShowJobs && (
                <div className="shrink-0 p-3 bg-slate-50 border-b border-[var(--border)] space-y-1.5 max-h-48 overflow-y-auto custom-scrollbar">
                     <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] font-bold text-[var(--muted)] uppercase tracking-wider">最近のジョブ ({jobs.length})</span>
                    </div>
                    {jobs.map(job => (
                        <OcrJobCard
                            key={job.file_path}
                            job={job}
                            onDismiss={dismissJob}
                            dismissing={dismissing.has(job.file_path)}
                        />
                    ))}
                </div>
            )}

            {/* [C] Upload Zone */}
            <div className="shrink-0 p-3 bg-white border-b border-[var(--border)]">
                <div
                    {...getRootProps()}
                    className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
                        isDragActive
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50'
                    }`}
                >
                    <input {...getInputProps()} />
                    {uploading ? (
                        <div className="flex flex-col items-center gap-1.5">
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500" />
                            <p className="text-[10px] font-medium text-blue-600">アップロード中...</p>
                        </div>
                    ) : (
                        <div>
                            <p className="text-[11px] font-semibold text-slate-600 mb-0.5">ここへドロップ / クリック</p>
                            <p className="text-[9px] text-slate-400">PDF, PNG, JPGをRAGに追加</p>
                        </div>
                    )}
                </div>
            </div>

            {/* [D] File List */}
            <div className="flex-1 flex flex-col min-h-0">
                <div className="flex items-center justify-between p-2 pl-3 bg-slate-50/50 border-b border-[var(--border)] shrink-0">
                    <span className="text-[10px] font-bold text-[var(--muted)] uppercase tracking-wider">ナレッジファイル ({flatFiles.length})</span>
                    <div className="flex items-center gap-1">
                        {selectedPaths.size > 0 && (
                            <button
                                onClick={confirmBulkDelete}
                                disabled={isDeleting}
                                className="px-2 py-1 bg-red-50 text-red-600 hover:bg-red-100 rounded text-[10px] font-bold flex items-center gap-1 transition-colors"
                            >
                                <Trash2 className="w-3 h-3" />
                                {selectedPaths.size}件削除
                            </button>
                        )}
                        <button onClick={fetchTree} className="p-1 hover:bg-slate-200 rounded text-slate-500">
                           <RefreshCw className={`w-3.5 h-3.5 ${treeLoading ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                </div>
                
                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    {treeLoading && flatFiles.length === 0 ? (
                         <div className="flex justify-center py-6"><div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
                    ) : flatFiles.length === 0 ? (
                         <div className="text-center py-8 text-slate-400">
                             <LibraryIcon className="w-6 h-6 mx-auto mb-2 opacity-50" />
                             <p className="text-[11px]">ファイルがありません</p>
                         </div>
                    ) : (
                        <div className="divide-y divide-[var(--border)]">
                            {flatFiles.map(file => (
                                <div 
                                    key={file.path}
                                    className="flex items-center gap-2 px-3 py-2 hover:bg-blue-50/50 cursor-pointer group transition-colors"
                                    onClick={() => setDetailFile(file)}
                                >
                                    <input
                                        type="checkbox"
                                        checked={selectedPaths.has(file.path)}
                                        onChange={(e) => { e.stopPropagation(); handleCheckToggle(file.path, e.target.checked); }}
                                        onClick={(e) => e.stopPropagation()}
                                        className="w-3.5 h-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500 shrink-0 cursor-pointer"
                                    />
                                    {file.name.endsWith('.pdf') ? (
                                        <FileText className="w-4 h-4 text-red-500 shrink-0" />
                                    ) : file.name.endsWith('.md') ? (
                                        <FileText className="w-4 h-4 text-violet-500 shrink-0" />
                                    ) : (
                                        <File className="w-4 h-4 text-slate-400 shrink-0" />
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <div className="text-[11px] font-medium text-slate-800 truncate group-hover:text-blue-700">{file.name}</div>
                                        <div className="flex items-center gap-2 mt-0.5">
                                            <span className="text-[9px] text-slate-400 font-mono">{formatSize(file.size)}</span>
                                            {file.ocr_status === 'completed' && <span className="text-[8px] px-1 py-0.5 bg-green-100 text-green-700 rounded border border-green-200">OCR済</span>}
                                            {file.ocr_status === 'processing' && <span className="text-[8px] px-1 py-0.5 bg-blue-100 text-blue-700 rounded border border-blue-200 flex items-center gap-0.5"><RefreshCw className="w-2 h-2 animate-spin" />処理中</span>}
                                            {file.ocr_status === 'failed' && <span className="text-[8px] px-1 py-0.5 bg-red-100 text-red-700 rounded border border-red-200">エラー</span>}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* [E] File Detail Modal */}
            {detailFile && (
                <div className="absolute inset-0 z-50 bg-white flex flex-col animate-in slide-in-from-bottom-2 duration-200">
                    <div className="flex items-center justify-between p-3 border-b border-[var(--border)] bg-slate-50 shrink-0">
                        <div className="flex items-center gap-2 min-w-0 pr-4">
                            <button onClick={() => setDetailFile(null)} className="p-1 hover:bg-slate-200 rounded text-slate-500 shrink-0">
                                <ChevronDown className="w-5 h-5 rotate-[90deg]" />
                            </button>
                            <div className="min-w-0">
                                <h3 className="text-sm font-bold text-slate-800 truncate">{detailFile.name}</h3>
                                <p className="text-[10px] text-slate-500 font-mono truncate">{detailFile.path}</p>
                            </div>
                        </div>
                    </div>
                    
                    <div className="flex-1 overflow-y-auto p-4 custom-scrollbar space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                            <div className="bg-slate-50 p-3 rounded-lg border border-[var(--border)]">
                                <div className="text-[10px] font-bold text-slate-500 uppercase mb-1">ファイルサイズ</div>
                                <div className="text-sm font-medium">{formatSize(detailFile.size)}</div>
                            </div>
                            <div className="bg-slate-50 p-3 rounded-lg border border-[var(--border)]">
                                <div className="text-[10px] font-bold text-slate-500 uppercase mb-1">OCRステータス</div>
                                <div className="text-sm font-medium flex items-center gap-1.5">
                                     {detailFile.ocr_status === 'completed' ? (
                                        <><div className="w-2 h-2 rounded-full bg-green-500" />完了</>
                                     ) : detailFile.ocr_status === 'processing' ? (
                                        <><div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />処理中</>
                                     ) : detailFile.ocr_status === 'failed' ? (
                                        <><div className="w-2 h-2 rounded-full bg-red-500" />エラー</>
                                     ) : (
                                        <><div className="w-2 h-2 rounded-full bg-slate-400" />未実行</>
                                     )}
                                </div>
                            </div>
                        </div>

                         <div className="bg-slate-50 p-3 rounded-lg border border-[var(--border)]">
                            <div className="text-[10px] font-bold text-slate-500 uppercase mb-2">アクション</div>
                            <div className="flex flex-col gap-2">
                                <a 
                                    href={`${API_BASE}/api/files/view/${detailFile.path.split('/').map(encodeURIComponent).join('/')}`} 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="flex items-center justify-center gap-2 w-full py-2 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-md text-xs font-bold transition-colors border border-blue-200"
                                >
                                    <Eye className="w-4 h-4" /> 新規タブでプレビュー
                                </a>
                                <a 
                                    href={`${API_BASE}/api/files/view/${detailFile.path.split('/').map(encodeURIComponent).join('/')}?download=true`} 
                                    download={detailFile.name}
                                    className="flex items-center justify-center gap-2 w-full py-2 bg-white text-slate-700 hover:bg-slate-50 rounded-md text-xs font-bold transition-colors border border-slate-300"
                                >
                                    <Download className="w-4 h-4" /> ダウンロード
                                </a>
                                <button
                                    onClick={async () => {
                                        if (confirm('削除しますか？')) {
                                            try {
                                                const res = await authFetch(`${API_BASE}/api/files/delete`, {
                                                    method: 'DELETE',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ file_path: detailFile.path })
                                                });
                                                if (res.ok) {
                                                    const data = await res.json();
                                                    if (data.errors && data.errors.length > 0) {
                                                        alert(`削除完了（一部エラー）:\n${data.errors.join('\n')}`);
                                                    }
                                                    setDetailFile(null);
                                                    fetchTree();
                                                    fetchStats();
                                                } else {
                                                    const data = await res.json().catch(() => ({}));
                                                    alert(`削除に失敗しました: ${data.detail || res.statusText}`);
                                                }
                                            } catch (e) {
                                                alert('削除中にエラーが発生しました');
                                            }
                                        }
                                    }}
                                    className="flex items-center justify-center gap-2 w-full py-2 bg-white text-red-600 hover:bg-red-50 rounded-md text-xs font-bold transition-colors border border-red-200 mt-2"
                                >
                                    <Trash2 className="w-4 h-4" /> このファイルを削除
                                </button>
                            </div>
                         </div>
                    </div>
                </div>
            )}
        </div>
    );
}
