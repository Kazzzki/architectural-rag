'use client';
import { authFetch } from '@/lib/api';

import React, { useState, useEffect } from 'react';
import {
    Folder,
    FileText,
    File,
    ChevronRight,
    ChevronDown,
    RefreshCw,
    Eye,
    Trash2,
    Download
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

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

export default function Library() {
    const [tree, setTree] = useState<FileNode | null>(null);
    const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
    const [deleteTarget, setDeleteTarget] = useState<FileNode | null>(null);
    const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
    const [isDeleting, setIsDeleting] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    const fetchTree = async () => {
        setIsLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/files/tree`);
            const data = await res.json();
            setTree(data);
        } catch (error) {
            console.error(error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchTree();
    }, []);

    const formatSize = (bytes?: number) => {
        if (bytes === undefined) return '-';
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const handleDeleteClick = (file: FileNode, e: React.MouseEvent) => {
        e.stopPropagation();
        setDeleteTarget(file);
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        setIsDeleting(true);

        try {
            const res = await authFetch(`${API_BASE}/api/files/delete`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: deleteTarget.path })
            });

            if (res.ok) {
                if (selectedFile?.path === deleteTarget.path) {
                    setSelectedFile(null);
                }
                fetchTree();
            } else {
                alert('削除に失敗しました');
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('削除エラーが発生しました');
        } finally {
            setIsDeleting(false);
            setDeleteTarget(null);
        }
    };

    const confirmBulkDelete = async () => {
        if (selectedPaths.size === 0) return;
        if (!window.confirm(`選択した ${selectedPaths.size} 件のファイルを完全に削除します。よろしいですか？`)) return;

        setIsDeleting(true);

        try {
            const res = await authFetch(`${API_BASE}/api/files/bulk-delete`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_paths: Array.from(selectedPaths) })
            });

            if (res.ok) {
                if (selectedFile && selectedPaths.has(selectedFile.path)) {
                    setSelectedFile(null);
                }
                setSelectedPaths(new Set());
                fetchTree();
            } else {
                alert('一括削除に失敗しました');
            }
        } catch (error) {
            console.error('Bulk delete error:', error);
            alert('一括削除エラーが発生しました');
        } finally {
            setIsDeleting(false);
        }
    };

    const handleCheckToggle = (node: FileNode, checked: boolean) => {
        const newSelected = new Set(selectedPaths);

        const toggleRecursive = (targetNode: FileNode, isChecked: boolean) => {
            if (targetNode.type === 'file') {
                if (isChecked) newSelected.add(targetNode.path);
                else newSelected.delete(targetNode.path);
            }
            if (targetNode.children) {
                targetNode.children.forEach(child => toggleRecursive(child, isChecked));
            }
        };

        toggleRecursive(node, checked);
        setSelectedPaths(newSelected);
    };

    const TreeNode = ({ node, level = 0 }: { node: FileNode, level?: number }) => {
        const [isOpen, setIsOpen] = useState(level < 2); // 2階層目まで開く（rootはlevel0）
        const isSelected = selectedFile?.path === node.path;

        const isChecked = node.type === 'file'
            ? selectedPaths.has(node.path)
            : node.children ? node.children.length > 0 && node.children.every(child => selectedPaths.has(child.path) || (child.type === 'directory')) : false;

        const isPartiallyChecked = node.type === 'directory'
            && node.children
            && node.children.some(child => selectedPaths.has(child.path))
            && !isChecked;

        if (node.type === 'file') {
            return (
                <div
                    className={`flex items-center gap-2 py-1 px-2 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 rounded ml-${level * 4} ${isSelected ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400' : ''}`}
                    style={{ marginLeft: `${level * 16}px` }}
                    onClick={() => setSelectedFile(node)}
                >
                    <input
                        type="checkbox"
                        checked={selectedPaths.has(node.path)}
                        onChange={(e) => {
                            e.stopPropagation();
                            handleCheckToggle(node, e.target.checked);
                        }}
                        className="w-3 h-3 text-blue-600 rounded border-slate-300 focus:ring-blue-500 cursor-pointer"
                        onClick={(e) => e.stopPropagation()}
                    />
                    {node.name.endsWith('.pdf') ? (
                        <FileText className="w-4 h-4 text-red-500" />
                    ) : node.name.endsWith('.md') ? (
                        <FileText className="w-4 h-4 text-blue-500" />
                    ) : (
                        <File className="w-4 h-4 text-slate-400" />
                    )}
                    <span className="text-sm truncate">{node.name}</span>
                    {node.ocr_status === 'completed' && (
                        <span className="text-[10px] bg-green-100 text-green-700 px-1 rounded ml-auto border border-green-200">OCR済</span>
                    )}
                    {node.ocr_status === 'processing' && node.ocr_progress && (
                        <div className="ml-auto flex items-center gap-1">
                            <RefreshCw className="w-3 h-3 animate-spin text-blue-500" />
                            <span className="text-[10px] text-blue-600 font-mono">
                                {Math.round((node.ocr_progress.current / node.ocr_progress.total) * 100)}%
                            </span>
                        </div>
                    )}
                    {node.ocr_status === 'failed' && (
                        <span className="text-[10px] bg-red-100 text-red-700 px-1 rounded ml-auto border border-red-200">エラー</span>
                    )}
                </div>
            );
        }

        return (
            <div>
                <div
                    className="flex items-center gap-2 py-1 px-2 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
                    style={{ marginLeft: `${level * 16}px` }}
                    onClick={() => setIsOpen(!isOpen)}
                >
                    <input
                        type="checkbox"
                        ref={(el) => { if (el) el.indeterminate = !!isPartiallyChecked; }}
                        checked={isChecked}
                        onChange={(e) => {
                            e.stopPropagation();
                            handleCheckToggle(node, e.target.checked);
                        }}
                        className="w-3 h-3 text-blue-600 rounded border-slate-300 focus:ring-blue-500 cursor-pointer disabled:opacity-50"
                        onClick={(e) => e.stopPropagation()}
                        disabled={!node.children || node.children.length === 0}
                    />
                    {isOpen ? (
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                    <Folder className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                    <span className="text-sm font-medium">{node.name}</span>
                </div>
                {isOpen && node.children && (
                    <div>
                        {node.children.map((child, i) => (
                            <TreeNode key={i} node={child} level={level + 1} />
                        ))}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="flex h-full gap-4 text-slate-800 dark:text-slate-200">
            {/* Tree View */}
            <div className="w-1/2 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg p-2 bg-white dark:bg-slate-900 h-[calc(100vh-200px)]">
                <div className="flex justify-between items-center mb-2 px-2 pb-2 border-b border-slate-100 dark:border-slate-800">
                    <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold">ファイル一覧</h3>
                        {selectedPaths.size > 0 && (
                            <button
                                onClick={confirmBulkDelete}
                                disabled={isDeleting}
                                className="flex items-center gap-1 bg-red-50 hover:bg-red-100 text-red-600 dark:bg-red-900/20 dark:hover:bg-red-900/40 dark:text-red-400 text-[10px] px-2 py-0.5 rounded transition-colors disabled:opacity-50"
                                title="選択した項目を一括削除"
                            >
                                <Trash2 className="w-3 h-3" />
                                {isDeleting ? '削除中...' : `${selectedPaths.size}件を削除`}
                            </button>
                        )}
                    </div>
                    <div className="flex items-center gap-1">
                        <a
                            href={`${API_BASE}/api/system/export-source`}
                            className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-colors text-slate-600 dark:text-slate-400"
                            title="ソースコードをダウンロード"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            <Download className="w-4 h-4" />
                        </a>
                        <button onClick={fetchTree} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-colors" title="更新">
                            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                </div>
                {tree ? (
                    <TreeNode node={tree} />
                ) : (
                    <div className="text-center py-4 text-sm text-slate-500">読み込み中...</div>
                )}
            </div>

            {/* Detail View */}
            <div className="w-1/2 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 h-[calc(100vh-200px)] flex flex-col">
                {selectedFile ? (
                    <div className="flex flex-col h-full">
                        {/* Header */}
                        <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex justify-between items-start bg-slate-50/50 dark:bg-slate-800/50">
                            <div className="overflow-hidden">
                                <h2 className="text-lg font-bold truncate" title={selectedFile.name}>{selectedFile.name}</h2>
                                <p className="text-xs text-slate-500 mt-1 font-mono truncate" title={selectedFile.path}>{selectedFile.path}</p>
                            </div>
                            <div className="flex items-center gap-2 ml-2">
                                <div className="flex bg-white dark:bg-slate-800 rounded border border-slate-200 dark:border-slate-700 text-xs shadow-sm shrink-0">
                                    <div className="px-3 py-1 border-r border-slate-200 dark:border-slate-700">
                                        {formatSize(selectedFile.size)}
                                    </div>
                                    <div className="px-3 py-1 font-semibold text-slate-600 dark:text-slate-300">
                                        {selectedFile.name.split('.').pop()?.toUpperCase()}
                                    </div>
                                </div>
                                <button
                                    onClick={(e) => handleDeleteClick(selectedFile, e)}
                                    className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
                                    title="削除"
                                >
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        </div>

                        {/* Preview Area */}
                        <div className="flex-1 overflow-hidden bg-slate-100 dark:bg-black/20 p-4">
                            {selectedFile.name.toLowerCase().endsWith('.pdf') ? (
                                <iframe
                                    src={`${API_BASE}/api/files/view/${selectedFile.path.split('/').map(encodeURIComponent).join('/')}`}
                                    className="w-full h-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white shadow-sm"
                                    title="PDF Preview"
                                />
                            ) : selectedFile.name.toLowerCase().endsWith('.md') ? (
                                <MarkdownPreview filePath={selectedFile.path} />
                            ) : (
                                <div className="h-full flex flex-col items-center justify-center text-slate-400 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 border-dashed">
                                    <File className="w-12 h-12 mb-3 opacity-20" />
                                    <p className="text-sm">プレビューできません</p>
                                    <a
                                        href={`${API_BASE}/api/files/view/${selectedFile.path}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="mt-4 text-xs text-blue-600 hover:underline flex items-center gap-1"
                                    >
                                        <Eye className="w-3 h-3" />
                                        ダウンロードして開く
                                    </a>
                                </div>
                            )}
                        </div>

                        {/* Footer / OCR Status */}
                        {selectedFile.ocr_status && (
                            <div className="p-3 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-xs">
                                {selectedFile.ocr_status === 'completed' ? (
                                    <div className="flex items-center text-green-600 gap-2">
                                        <div className="w-2 h-2 rounded-full bg-green-500" />
                                        <span>OCR完了: 検索インデックスに含まれています</span>
                                    </div>
                                ) : selectedFile.ocr_status === 'processing' ? (
                                    <div className="space-y-2">
                                        <div className="flex items-center text-blue-600 gap-2">
                                            <RefreshCw className="w-3 h-3 animate-spin" />
                                            <span className="font-bold">OCR処理中...</span>
                                            {selectedFile.ocr_progress && (
                                                <span className="ml-auto text-slate-500 font-mono">
                                                    {selectedFile.ocr_progress.current} / {selectedFile.ocr_progress.total} ページ ({Math.round(selectedFile.ocr_progress.current / selectedFile.ocr_progress.total * 100)}%)
                                                </span>
                                            )}
                                        </div>
                                        {selectedFile.ocr_progress && (
                                            <div className="w-full bg-slate-200 rounded-full h-1.5 dark:bg-slate-700 overflow-hidden">
                                                <div
                                                    className="bg-blue-500 h-1.5 rounded-full transition-all duration-500"
                                                    style={{ width: `${(selectedFile.ocr_progress.current / selectedFile.ocr_progress.total) * 100}%` }}
                                                />
                                            </div>
                                        )}
                                        {selectedFile.ocr_progress?.estimated_remaining && (
                                            <div className="text-right text-slate-400 text-[10px]">
                                                残り時間: 約 {selectedFile.ocr_progress.estimated_remaining} 秒
                                            </div>
                                        )}
                                    </div>
                                ) : selectedFile.ocr_status === 'failed' ? (
                                    <div className="flex flex-col gap-1 text-red-600">
                                        <div className="flex items-center gap-2 font-bold">
                                            <div className="w-2 h-2 rounded-full bg-red-500" />
                                            <span>OCRエラー</span>
                                        </div>
                                        {selectedFile.ocr_progress?.error && (
                                            <p className="pl-4 text-[10px] text-red-500 break-all">
                                                {selectedFile.ocr_progress.error}
                                            </p>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center text-yellow-600 gap-2">
                                        <div className="w-2 h-2 rounded-full bg-yellow-500" />
                                        <span>OCR未実行</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                        <FileText className="w-16 h-16 mb-4 opacity-20" />
                        <p className="text-sm font-medium">ファイルを選択してください</p>
                        <p className="text-xs mt-2 text-slate-500">左側のツリーからファイルを選んでプレビューを表示</p>
                    </div>
                )}
            </div>

            {/* Delete Confirmation Modal */}
            {deleteTarget && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-slate-900 rounded-lg shadow-xl max-w-sm w-full p-6 border border-slate-200 dark:border-slate-800 animate-in zoom-in-95 duration-200">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100 mb-2">
                            ファイルを削除しますか？
                        </h3>
                        <p className="text-sm text-slate-600 dark:text-slate-400 mb-6 break-all">
                            「{deleteTarget.name}」<br />
                            この操作は取り消せません。検索インデックスからも削除されます。
                        </p>
                        <div className="flex justify-end gap-3">
                            <button
                                onClick={() => setDeleteTarget(null)}
                                className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md transition-colors"
                                disabled={isDeleting}
                            >
                                キャンセル
                            </button>
                            <button
                                onClick={confirmDelete}
                                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md shadow-sm transition-colors flex items-center gap-2"
                                disabled={isDeleting}
                            >
                                {isDeleting && <RefreshCw className="w-3 h-3 animate-spin" />}
                                削除する
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// Markdown Preview Component
function MarkdownPreview({ filePath }: { filePath: string }) {
    const [content, setContent] = useState<string>('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        setLoading(true);
        authFetch(`${API_BASE}/api/files/view/${filePath}`)
            .then(res => res.text())
            .then(text => setContent(text))
            .catch(err => setContent('読み込みエラー'))
            .finally(() => setLoading(false));
    }, [filePath]);

    if (loading) return <div className="h-full flex items-center justify-center text-slate-400"><RefreshCw className="animate-spin w-5 h-5" /></div>;

    // ReactMarkdownを動的インポートしないとNext.jsでエラーになる場合があるが、
    // ここでは単純にインポートしてみる。もしエラーならDynamic Importに切り替える。
    // しかし今回は import ReactMarkdown from 'react-markdown' をファイルの先頭に追加する必要がある。
    // このreplace_file_contentではファイルの途中しか書き換えていないので、import文が足りない可能性がある。

    // 既存のコードには import ReactMarkdown はない。
    // したがって、ファイルの先頭も書き換える必要がある。
    // しかし tool は1回1チャンク。
    // まずはコンポーネント定義だけ書き換え、次のステップで import を追加する。

    return (
        <div className="h-full overflow-y-auto bg-white dark:bg-slate-900 p-6 rounded-lg border border-slate-200 dark:border-slate-700 shadow-sm prose dark:prose-invert max-w-none text-sm">
            <ReactMarkdown>{content}</ReactMarkdown>
        </div>
    );
}
