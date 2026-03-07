'use client';
import React from 'react';

import { authFetch, fetchSessions, createSession, fetchSessionDetail, deleteSession, saveMessages, SessionSummary } from '@/lib/api';
import { resolvePdfUrl } from '@/lib/pdf';

import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import {
    Send,
    Upload,
    RefreshCw,
    Building2,
    FileText,
    ChevronDown,
    Loader2,
    X,
    Check,
    Cloud,
    CloudOff,
    ExternalLink,
    UploadCloud,
    Library as LibraryIcon,
    MessageSquare,
    Map,
    Sparkles
} from 'lucide-react';
import Link from 'next/link';
import Library from './components/Library';
import FileUpload from './components/FileUpload';
import StatsPanel from './components/StatsPanel';
import ContextSheetPanel from './components/ContextSheetPanel';
import ScopeEnginePanel from './components/ScopeEnginePanel';
import dynamic from 'next/dynamic';

const PDFViewer = dynamic(() => import('./components/PDFViewer'), {
    ssr: false,
    loading: () => <div className="p-4 text-center">Loading PDF Viewer...</div>
});

// Types
interface Message {
    role: 'user' | 'assistant';
    content: string;
    sources?: SourceFile[];
}

interface SourceFile {
    source_id: string;
    filename: string;
    original_filename?: string;
    source_pdf_name: string;
    source_pdf: string;
    source_pdf_hash: string;
    rel_path: string;
    category: string;
    doc_type: string;
    pages: number[];
    hit_count: number;
    relevance_count: number;
    pdf_filename?: string;
}

interface Stats {
    file_count: number;
    chunk_count: number;
    last_updated: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// ─── doc_type バッジ ────────────────────────────────────────────────────────────
const DOC_TYPE_BADGE: Record<string, { label: string; cls: string }> = {
    drawing: { label: '📐 図面', cls: 'bg-blue-500/15 text-blue-300 border-blue-500/30' },
    law: { label: '⚖️ 法規', cls: 'bg-red-500/15 text-red-300 border-red-500/30' },
    spec: { label: '📋 仕様書', cls: 'bg-green-500/15 text-green-300 border-green-500/30' },
    catalog: { label: '📦 カタログ', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
};

// ─── SourceCard コンポーネント ─────────────────────────────────────────────────
const PAGE_CHIP_LIMIT = 5;

function SourceCard({
    src,
    onPageClick,
}: {
    src: SourceFile;
    onPageClick: (url: string, page: number) => void;
}) {
    const [expanded, setExpanded] = useState(false);
    const badge = DOC_TYPE_BADGE[src.doc_type];
    const relevanceDots = src.hit_count >= 3 ? '●●●' : src.hit_count === 2 ? '●●○' : '●○○';

    const visiblePages = expanded ? src.pages : src.pages.slice(0, PAGE_CHIP_LIMIT);
    const hiddenCount = src.pages.length - PAGE_CHIP_LIMIT;
    const resolvedUrl = resolvePdfUrl(src);

    return (
        <div className="flex flex-col gap-1.5 bg-[var(--card)] border border-[var(--border)] px-3 py-2 rounded-lg text-xs min-w-[180px] max-w-[260px] relative">
            {/* source_id + doc_type badge */}
            <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-bold text-[var(--muted)] bg-[var(--background)] border border-[var(--border)] px-1.5 py-0.5 rounded">
                    {src.source_id}
                </span>
                {badge && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.cls}`}>
                        {badge.label}
                    </span>
                )}
                <span className="ml-auto text-[10px] text-[var(--muted)]" title={`ヒット数: ${src.hit_count}`}>
                    {relevanceDots}
                </span>
            </div>

            {/* Filename */}
            <div className="flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-primary-500 shrink-0" />
                <span className="font-medium text-[var(--foreground)] truncate">
                    {src.original_filename || src.source_pdf_name || src.filename}
                </span>
            </div>

            {/* Page chips */}
            {src.pages.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-0.5">
                    {visiblePages.map((p) => {
                        return resolvedUrl ? (
                            <button
                                key={p}
                                onClick={() => onPageClick(resolvedUrl, p)}
                                className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/30 hover:bg-blue-500/20 transition-colors cursor-pointer"
                            >
                                p.{p}
                            </button>
                        ) : (
                            <span key={p} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--background)] text-[var(--muted)] border border-[var(--border)]">
                                p.{p}
                            </span>
                        );
                    })}
                    {!expanded && hiddenCount > 0 && (
                        <button
                            onClick={() => setExpanded(true)}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--background)] text-[var(--muted)] border border-[var(--border)] hover:bg-[var(--card-hover)] transition-colors"
                        >
                            +{hiddenCount}
                        </button>
                    )}
                    {expanded && hiddenCount > 0 && (
                        <button
                            onClick={() => setExpanded(false)}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--background)] text-[var(--muted)] border border-[var(--border)] hover:bg-[var(--card-hover)] transition-colors"
                        >
                            折りたたむ
                        </button>
                    )}
                </div>
            )}

            {/* Fallback: no pages, but PDF openable */}
            {src.pages.length === 0 && resolvedUrl && (
                <button
                    onClick={() => onPageClick(resolvedUrl, 1)}
                    className="text-[10px] text-blue-500 hover:text-blue-600 flex items-center gap-0.5 border border-blue-200 bg-blue-50 dark:border-blue-900/40 dark:bg-blue-900/10 px-1.5 py-0.5 rounded self-start"
                >
                    <ExternalLink className="w-2.5 h-2.5" />
                    📄 PDF表示
                </button>
            )}
        </div>
    );
}

// ─── CitationBadge コンポーネント ──────────────────────────────────────────────
const CITATION_PATTERN = /\[S(\d+):p\.(\d+)\]/g;

function CitationBadge({
    sourceId,
    page,
    sources,
    onPageClick,
}: {
    sourceId: string;
    page: number;
    sources: SourceFile[];
    onPageClick: (url: string, page: number) => void;
}) {
    const src = sources.find((s) => s.source_id === sourceId);

    if (!src) {
        // 対応ソースが見つからない場合はプレーンテキスト
        return <span>[{sourceId}:p.{page}]</span>;
    }

    const url = resolvePdfUrl(src);

    if (!url) {
        return (
            <span className="inline-flex items-center text-[11px] px-1.5 py-0.5 mx-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">
                {sourceId} p.{page}
            </span>
        );
    }

    return (
        <button
            onClick={() => onPageClick(url, page)}
            className="inline-flex items-center text-[11px] px-1.5 py-0.5 mx-0.5 rounded bg-blue-500/15 text-blue-400 border border-blue-500/30 hover:bg-blue-500/25 hover:text-blue-300 transition-colors cursor-pointer font-mono"
            title={`${src.source_pdf_name || src.filename} p.${page} を開く`}
        >
            {sourceId} p.{page}
        </button>
    );
}

// テキストノード内の [S1:p.12] パターンを CitationBadge に変換
function transformCitations(
    text: string,
    sources: SourceFile[],
    onPageClick: (url: string, page: number) => void
): React.ReactNode {
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    const regex = new RegExp(CITATION_PATTERN.source, 'g');
    let match;
    while ((match = regex.exec(text)) !== null) {
        if (match.index > lastIndex) {
            parts.push(text.slice(lastIndex, match.index));
        }
        const sourceId = `S${match[1]}`;
        const page = parseInt(match[2], 10);
        parts.push(
            <CitationBadge
                key={`${sourceId}-${page}-${match.index}`}
                sourceId={sourceId}
                page={page}
                sources={sources}
                onPageClick={onPageClick}
            />
        );
        lastIndex = match.index + match[0].length;
    }
    if (lastIndex < text.length) {
        parts.push(text.slice(lastIndex));
    }
    return parts.length === 1 && typeof parts[0] === 'string' ? parts[0] : <>{parts}</>;
}

const EXAMPLE_QUESTIONS = [
    'ALCとECPの防水性能・コスト・メンテナンス性の違いを比較して',
    'S造事務所の外壁矩計図で確認すべきポイントは？',
    'サッシの気密・水密・耐風圧等級の選定基準を教えて',
    'シーリングの種類と使い分け',
    '屋根防水でアスファルト防水と塩ビシート防水の比較',
];

const CATEGORIES = [
    { value: '', label: '全て（横断検索）' },
    { value: '01_カタログ', label: '01 カタログ' },
    { value: '02_図面', label: '02 図面' },
    { value: '03_技術基準', label: '03 技術基準' },
    { value: '04_リサーチ成果物', label: '04 リサーチ成果物' },
    { value: '05_法規', label: '05 法規' },
    { value: '06_設計マネジメント', label: '06 設計マネジメント' },
    { value: '07_コストマネジメント', label: '07 コストマネジメント' },
    { value: '00_未分類', label: '00 未分類' },
];

export default function Home() {
    // State definitions
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    // Session Management State
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const [sessions, setSessions] = useState<SessionSummary[]>([]);
    const [showSessionList, setShowSessionList] = useState(true);

    // Filters
    const [category, setCategory] = useState('');
    const [fileType, setFileType] = useState('');
    const [dateRange, setDateRange] = useState('');
    const [availableTags, setAvailableTags] = useState<Record<string, string[]>>({});
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [tagMatchMode, setTagMatchMode] = useState<'any' | 'all'>('any');
    const [isTagExpanded, setIsTagExpanded] = useState(false);

    const [stats, setStats] = useState<Stats | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadResult, setUploadResult] = useState<string | null>(null);
    const [isIndexing, setIsIndexing] = useState(false);
    const [driveStatus, setDriveStatus] = useState<{ authenticated: boolean, message: string } | null>(null);
    const [isSyncing, setIsSyncing] = useState(false);
    const [syncResult, setSyncResult] = useState<string | null>(null);
    const [isUploadingToDrive, setIsUploadingToDrive] = useState(false);
    const [activeTab, setActiveTab] = useState<'chat' | 'library'>('chat');
    const [pdfUrl, setPdfUrl] = useState<string | null>(null);
    const [pdfInitialPage, setPdfInitialPage] = useState(1);
    const [isPdfOpen, setIsPdfOpen] = useState(false);

    // --- Scope Engine ---
    const [projectId, setProjectId] = useState<string | null>(null);
    const [scopeMode, setScopeMode] = useState<string>('auto');
    const [useRag, setUseRag] = useState<boolean>(true);

    // --- コンテキストシート機能 ---
    const [availableModels, setAvailableModels] = useState<Record<string, string>>({});
    const [availableRoles, setAvailableRoles] = useState<Record<string, string>>({});
    const [selectedModel, setSelectedModel] = useState('gemini-3-flash-preview');
    const [activeContextSheet, setActiveContextSheet] = useState<string | null>(null);
    const [activeSheetTitle, setActiveSheetTitle] = useState<string | null>(null);
    const [activeContextRole, setActiveContextRole] = useState<string | null>(null);
    const [isGeneratingSheet, setIsGeneratingSheet] = useState(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    useEffect(() => {
        const loadInitialSession = async () => {
            try {
                const fetchedSessions = await fetchSessions();
                setSessions(fetchedSessions);
                if (fetchedSessions.length > 0) {
                    const latestSession = fetchedSessions[0];
                    const detail = await fetchSessionDetail(latestSession.id);
                    setActiveSessionId(detail.id);
                    setMessages(detail.messages.map(m => ({
                        role: m.role as 'user' | 'assistant',
                        content: m.content,
                        sources: m.sources
                    })));
                } else {
                    const newSession = await createSession();
                    setActiveSessionId(newSession.id);
                }
            } catch (err) {
                console.error('Failed to load sessions', err);
            }
        };
        loadInitialSession();
    }, []);

    const fetchStats = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/stats`);
            if (res.ok) {
                const data = await res.json();
                setStats(data);
            }
        } catch (error) {
            console.error('Stats fetch error:', error);
        }
    }, []);

    const fetchTags = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/tags`);
            if (res.ok) {
                const data = await res.json();
                setAvailableTags(data);
            }
        } catch (error) {
            console.error('Tags fetch error:', error);
        }
    }, []);

    const fetchModels = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/models`);
            if (res.ok) {
                const data = await res.json();
                setAvailableModels(data);
            }
        } catch (error) {
            console.error('Models fetch error:', error);
        }
    }, []);

    const fetchRoles = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/roles`);
            if (res.ok) {
                const data = await res.json();
                setAvailableRoles(data);
            }
        } catch (error) {
            console.error('Roles fetch error:', error);
        }
    }, []);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('auth') === 'success') {
            alert('認証が完了しました！');
            window.history.replaceState(null, '', window.location.pathname);
        }

        fetchStats();
        fetchTags();
        fetchModels();
        fetchRoles();
        checkDriveStatus();
    }, [fetchStats, fetchTags, fetchModels, fetchRoles]);

    const checkDriveStatus = async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/drive/status`);
            if (res.ok) {
                const data = await res.json();
                setDriveStatus(data);
            }
        } catch (error) {
            setDriveStatus({ authenticated: false, message: '接続エラー' });
        }
    };

    const handleDriveAuth = async () => {
        try {
            // Next.js proxy (/api/*) 経由でバックエンドに送信 — 相対パスで CORS を回避
            const currentHost = window.location.host;
            const currentProto = window.location.protocol.replace(':', '');

            const res = await authFetch(`/api/drive/auth`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Forwarded-Host': currentHost,
                    'X-Forwarded-Proto': currentProto
                }
            });
            if (res.ok) {
                const data = await res.json();
                if (data.auth_url) {
                    window.location.href = data.auth_url;
                } else {
                    alert('auth_url が返されませんでした: ' + JSON.stringify(data));
                }
            } else {
                const errText = await res.text();
                console.error('Drive auth failed:', res.status, errText);
                alert(`Drive認証エラー (${res.status}): ${errText.slice(0, 200)}`);
            }
        } catch (error) {
            console.error('Drive auth error:', error);
            alert(`接続エラー: ${error}`);
        }
    };

    const handleDriveSync = async () => {
        setIsSyncing(true);
        setSyncResult(null);
        try {
            const res = await authFetch(`${API_BASE}/api/drive/sync`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_name: '建築意匠ナレッジDB' }),
            });
            if (res.ok) {
                const data = await res.json();
                setSyncResult(`${data.downloaded}件ダウンロード`);
                fetchStats();
            } else {
                const err = await res.json();
                setSyncResult(err.detail || '同期失敗');
            }
        } catch (error) {
            setSyncResult('同期エラー');
        } finally {
            setIsSyncing(false);
        }
    };

    const handleDriveUpload = async () => {
        if (!confirm('Google Driveへファイルを同期（アップロード）しますか？\n（同名ファイルは上書きされます）')) return;
        setIsUploadingToDrive(true);
        try {
            const res = await authFetch(`${API_BASE}/api/sync-drive`, { method: 'POST' });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || '同期失敗');
            }
            const data = await res.json();
            const stats = data.stats || {};
            alert(`同期完了しました。\n作成: ${stats.created}, 更新: ${stats.updated}, エラー: ${stats.errors}`);
        } catch (error: any) {
            console.error('Sync Error:', error);
            alert(`同期に失敗しました: ${error.message || '不明なエラー'}`);
        } finally {
            setIsUploadingToDrive(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        const userMessage = input.trim();
        setInput('');

        // 現在の会話履歴を送信前にキャプチャ（新しいメッセージを追加する前）
        const historySnapshot = messages.map(m => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
        }));

        // Add user message
        setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

        // Add placeholder assistant message
        setMessages(prev => [...prev, {
            role: 'assistant',
            content: '',
            sources: undefined
        }]);

        setIsLoading(true);

        try {
            const { chatStream } = await import('../lib/api');
            let accumulatedAnswer = '';
            let currentSources: SourceFile[] = [];

            for await (const update of chatStream(
                userMessage,
                category,
                fileType,
                dateRange,
                selectedTags.length > 0 ? selectedTags : undefined,
                tagMatchMode,
                historySnapshot.length > 0 ? historySnapshot : undefined,
                selectedModel,
                activeContextSheet,
                true,       // quickMode
                projectId,
                scopeMode,
                useRag
            )) {
                if (update.type === 'sources') {
                    currentSources = update.data;
                    setMessages(prev => {
                        const newMessages = [...prev];
                        const lastMsg = newMessages[newMessages.length - 1];
                        if (lastMsg.role === 'assistant') {
                            lastMsg.sources = update.data;
                        }
                        return newMessages;
                    });
                } else if (update.type === 'answer') {
                    accumulatedAnswer += update.data;
                    setMessages(prev => {
                        const newMessages = [...prev];
                        const lastMsg = newMessages[newMessages.length - 1];
                        if (lastMsg.role === 'assistant') {
                            lastMsg.content = accumulatedAnswer;
                        }
                        return newMessages;
                    });
                }
            }

            // Stream complete. Save to DB.
            let sessionIdToSave = activeSessionId;
            if (!sessionIdToSave) {
                const newSession = await createSession();
                sessionIdToSave = newSession.id;
                setActiveSessionId(newSession.id);
            }
            try {
                await saveMessages(sessionIdToSave, {
                    user: userMessage,
                    assistant: accumulatedAnswer,
                    sources: currentSources,
                    model: selectedModel
                });
                const fetchedSessions = await fetchSessions();
                setSessions(fetchedSessions);
            } catch (saveErr) {
                console.error('Failed to save message:', saveErr);
            }

        } catch (error) {
            setMessages(prev => {
                const newMessages = [...prev];
                const lastMsg = newMessages[newMessages.length - 1];
                if (lastMsg.role === 'assistant') {
                    lastMsg.content += '\n\n(エラーが発生しました。通信を確認してください)';
                }
                return newMessages;
            });
        } finally {
            setIsLoading(false);
        }
    };

    const handleExampleClick = (question: string) => {
        setInput(question);
    };

    // シート生成中のSSEチャンクをチャット画面にstreamingDisplayするハンドラー
    const handleSheetStreamStart = () => {
        setIsGeneratingSheet(true);
        setMessages(prev => [...prev, { role: 'assistant', content: '', sources: undefined }]);
    };

    const handleSheetStreamChunk = (chunk: string) => {
        setMessages(prev => {
            const msgs = [...prev];
            const last = msgs[msgs.length - 1];
            if (last?.role === 'assistant') last.content += chunk;
            return msgs;
        });
    };

    const handleSheetStreamEnd = () => {
        setIsGeneratingSheet(false);
    };

    const handleSheetApplied = (content: string, title: string, role: string) => {
        setActiveContextSheet(content);
        setActiveSheetTitle(title);
        setActiveContextRole(role);
    };

    // Replaced with FileUpload component, but keeping this for legacy multiple file upload via button if needed
    // Currently hidden in UI
    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        setIsUploading(true);
        setUploadResult(null);

        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
        }
        formData.append('category', 'uploads');

        try {
            const res = await authFetch(`${API_BASE}/api/upload/multiple`, {
                method: 'POST',
                body: formData,
            });

            if (res.ok) {
                const data = await res.json();
                setUploadResult(`${data.uploaded.length}ファイルをアップロードしました`);
                fetchStats();
            } else {
                setUploadResult('アップロードに失敗しました');
            }
        } catch (error) {
            setUploadResult('アップロードエラー');
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }
    };

    const handleReindex = async () => {
        setIsIndexing(true);
        try {
            const res = await authFetch(`${API_BASE}/api/index`, { method: 'POST' });
            if (res.ok) {
                fetchStats();
            }
        } catch (error) {
            console.error('Reindex error:', error);
        } finally {
            setIsIndexing(false);
        }
    };

    return (
        <div className="min-h-screen flex flex-col">
            {/* Header */}
            <header className="border-b border-[var(--border)] bg-[var(--card)]/50 backdrop-blur-sm sticky top-0 z-10">
                <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center">
                            <Building2 className="w-6 h-6 text-white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold bg-gradient-to-r from-primary-400 to-accent-400 bg-clip-text text-transparent">
                                建築意匠ナレッジベース
                            </h1>
                            <p className="text-xs text-[var(--muted)]">PM/CM技術アドバイザー</p>
                        </div>
                    </div>

                    {/* Navigation Links */}
                    <div className="flex items-center gap-2">
                        <Link
                            href="/my-context"
                            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-teal-500/20 to-emerald-500/20 border border-teal-500/30 text-teal-300 hover:from-teal-500/30 hover:to-emerald-500/30 hover:border-teal-500/50 transition-all text-sm font-medium"
                        >
                            <LibraryIcon className="w-4 h-4" />
                            My Context
                        </Link>
                        <Link
                            href="/mindmap"
                            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-violet-500/20 to-fuchsia-500/20 border border-violet-500/30 text-violet-300 hover:from-violet-500/30 hover:to-fuchsia-500/30 hover:border-violet-500/50 transition-all text-sm font-medium"
                        >
                            <Map className="w-4 h-4" />
                            プロセスマップ
                        </Link>

                    </div>

                    {/* Stats */}
                    {stats && (
                        <div className="hidden md:flex items-center gap-4 text-sm text-[var(--muted)]">
                            <span className="flex items-center gap-1">
                                <FileText className="w-4 h-4" />
                                {stats.file_count}ファイル
                            </span>
                            <span>{stats.chunk_count}チャンク</span>
                        </div>
                    )}
                </div>
            </header>

            {/* Main Content */}
            <div className="flex-1 max-w-6xl mx-auto w-full flex flex-col md:flex-row gap-4 p-4">
                {/* Sidebar */}
                <aside className="md:w-64 space-y-4">
                    <ScopeEnginePanel onScopeChange={(pid, sm) => { setProjectId(pid); setScopeMode(sm); }} />

                    {/* Session List */}
                    <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)] shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <label className="block text-sm font-medium flex items-center gap-2">
                                <MessageSquare className="w-4 h-4" />
                                チャット履歴
                            </label>
                            <button
                                onClick={() => setShowSessionList(!showSessionList)}
                                className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                            >
                                <ChevronDown className={`w-4 h-4 transition-transform ${showSessionList ? 'rotate-180' : ''}`} />
                            </button>
                        </div>

                        {showSessionList && (
                            <div className="space-y-1 max-h-48 overflow-y-auto pr-1 animate-fade-in custom-scrollbar">
                                {sessions.length === 0 ? (
                                    <div className="text-xs text-[var(--muted)] text-center py-4 bg-[var(--background)] rounded-lg border border-[var(--border)] border-dashed">履歴がありません</div>
                                ) : (
                                    sessions.map(s => (
                                        <div key={s.id} className={`group flex items-center justify-between p-2 rounded-lg text-xs cursor-pointer transition-all border border-transparent ${activeSessionId === s.id ? 'bg-primary-500/10 text-primary-600 border-primary-500/20 shadow-sm' : 'hover:bg-[var(--card-hover)] text-[var(--foreground)] hover:border-[var(--border)]'}`} onClick={async () => {
                                            try {
                                                const detail = await fetchSessionDetail(s.id);
                                                setActiveSessionId(s.id);
                                                setMessages(detail.messages.map(m => ({ role: m.role as 'user' | 'assistant', content: m.content, sources: m.sources })));
                                            } catch (e) { console.error('Failed to load session', e); }
                                        }}>
                                            <div className="flex-1 overflow-hidden">
                                                <div className="truncate font-medium">{s.title || '新規チャット'}</div>
                                                <div className="text-[10px] text-[var(--muted)] mt-0.5">{new Date(s.updated_at).toLocaleString('ja-JP', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</div>
                                            </div>
                                            <button
                                                onClick={async (e) => {
                                                    e.stopPropagation();
                                                    if (confirm('この履歴を削除しますか？')) {
                                                        try {
                                                            await deleteSession(s.id);
                                                            if (activeSessionId === s.id) {
                                                                setMessages([]);
                                                                setActiveSessionId(null);
                                                            }
                                                            fetchSessions().then(setSessions);
                                                        } catch (err) { console.error(err); }
                                                    }
                                                }}
                                                className="text-[var(--muted)] hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all p-1.5 rounded-md hover:bg-red-500/10"
                                                title="削除"
                                            >
                                                <X className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    ))
                                )}
                            </div>
                        )}
                    </div>

                    {/* Stats Dashboard (Phase 4-1) */}
                    <div className="md:hidden">
                        {/* Mobile only here, or duplicate? The component design is 3 cols, fits sidebar width? 
                            Sidebar is w-64 (256px). 3 cols might be tight. 
                            Let's put it at the top of Sidebar but maybe stack vertically if needed or just use it. 
                            Actually the design in StatsPanel is grid-cols-3. 
                            Let's assume it fits or style adjusts. 
                        */}
                    </div >
                    <StatsPanel stats={stats} onRefresh={fetchStats} isLoading={false} />

                    {/* File Upload Component (New) */}
                    <FileUpload />

                    {/* Category Filter */}
                    <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)]">
                        <label className="block text-sm font-medium mb-2">検索対象</label>
                        <div className="relative">
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500"
                            >
                                {CATEGORIES.map((cat) => (
                                    <option key={cat.value} value={cat.value}>
                                        {cat.label}
                                    </option>
                                ))}
                            </select>
                            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted)] pointer-events-none" />
                        </div>
                    </div>



                    {/* Search Filters (Phase 4-2) */}
                    <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)] space-y-3">
                        <label className="block text-sm font-medium">絞り込み</label>

                        {/* File Type Filter */}
                        <div className="relative">
                            <select
                                className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500"
                                value={fileType}
                                onChange={(e) => setFileType(e.target.value)}
                            >
                                <option value="">全てのファイル形式</option>
                                <option value=".pdf">PDFドキュメント</option>
                                <option value=".md">Markdown</option>
                                <option value=".txt">テキスト</option>
                            </select>
                            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--muted)] pointer-events-none" />
                        </div>

                        {/* Date Filter */}
                        <div className="relative">
                            <select
                                className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500"
                                value={dateRange}
                                onChange={(e) => setDateRange(e.target.value)}
                            >
                                <option value="">全期間</option>
                                <option value="7d">過去1週間</option>
                                <option value="1m">過去1ヶ月</option>
                                <option value="3m">過去3ヶ月</option>
                            </select>
                            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--muted)] pointer-events-none" />
                        </div>

                        {/* Tag Filter (Phase 4-4) */}
                        <div className="pt-2 border-t border-[var(--border)]">
                            <button
                                onClick={() => setIsTagExpanded(!isTagExpanded)}
                                className="flex items-center justify-between w-full text-xs font-medium text-[var(--foreground)] mb-2"
                            >
                                <span>タグフィルター ({selectedTags.length})</span>
                                <ChevronDown className={`w-3 h-3 transition-transform ${isTagExpanded ? 'rotate-180' : ''}`} />
                            </button>

                            {isTagExpanded && (
                                <div className="space-y-3 animate-fade-in">
                                    <div className="flex items-center gap-2 text-xs mb-2 bg-[var(--background)] p-1 rounded-lg border border-[var(--border)]">
                                        <button
                                            onClick={() => setTagMatchMode('any')}
                                            className={`flex-1 py-1 rounded-md transition-colors ${tagMatchMode === 'any' ? 'bg-primary-100 text-primary-700' : 'text-[var(--muted)] hover:bg-[var(--card-hover)]'}`}
                                        >
                                            Any
                                        </button>
                                        <button
                                            onClick={() => setTagMatchMode('all')}
                                            className={`flex-1 py-1 rounded-md transition-colors ${tagMatchMode === 'all' ? 'bg-primary-100 text-primary-700' : 'text-[var(--muted)] hover:bg-[var(--card-hover)]'}`}
                                        >
                                            All
                                        </button>
                                    </div>

                                    <div className="max-h-60 overflow-y-auto pr-1 space-y-4">
                                        {Object.entries(availableTags).map(([group, tags]) => (
                                            <div key={group}>
                                                <h4 className="text-[10px] uppercase tracking-wider text-[var(--muted)] mb-1.5 font-bold">
                                                    {group}
                                                </h4>
                                                <div className="space-y-1">
                                                    {tags.map((tag) => (
                                                        <label key={tag} className="flex items-center gap-2 cursor-pointer group hover:bg-[var(--background)] p-1 rounded-md transition-colors">
                                                            <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${selectedTags.includes(tag)
                                                                ? 'bg-primary-500 border-primary-500'
                                                                : 'border-[var(--border)] group-hover:border-primary-400'
                                                                }`}>
                                                                {selectedTags.includes(tag) && <Check className="w-3 h-3 text-white" />}
                                                            </div>
                                                            <input
                                                                type="checkbox"
                                                                className="hidden"
                                                                checked={selectedTags.includes(tag)}
                                                                onChange={() => {
                                                                    setSelectedTags(prev =>
                                                                        prev.includes(tag)
                                                                            ? prev.filter(t => t !== tag)
                                                                            : [...prev, tag]
                                                                    );
                                                                }}
                                                            />
                                                            <span className={`text-xs ${selectedTags.includes(tag) ? 'text-primary-600 font-medium' : 'text-[var(--foreground)]'}`}>
                                                                {tag}
                                                            </span>
                                                        </label>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    {selectedTags.length > 0 && (
                                        <button
                                            onClick={() => setSelectedTags([])}
                                            className="w-full text-xs text-[var(--muted)] hover:text-[var(--foreground)] py-1 text-center border-t border-[var(--border)] mt-2"
                                        >
                                            クリア
                                        </button>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Google Drive Sync */}
                    <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)]">
                        <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                            <Cloud className="w-4 h-4" />
                            Google Drive
                        </label>
                        {driveStatus?.authenticated ? (
                            <div className="space-y-2">
                                <button
                                    onClick={handleDriveSync}
                                    disabled={isSyncing}
                                    className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 rounded-lg px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50"
                                >
                                    {isSyncing ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <RefreshCw className="w-4 h-4" />
                                    )}
                                    {isSyncing ? '同期中...' : 'Driveから同期'}
                                </button>

                                <button
                                    onClick={handleDriveUpload}
                                    disabled={isUploadingToDrive}
                                    className="w-full flex items-center justify-center gap-2 bg-[var(--background)] hover:bg-[var(--card-hover)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm transition-colors disabled:opacity-50"
                                >
                                    <UploadCloud className={`w-4 h-4 ${isUploadingToDrive ? 'animate-bounce' : ''}`} />
                                    {isUploadingToDrive ? 'アップロード中...' : 'Driveへバックアップ'}
                                </button>

                                <p className="text-xs mt-2 text-green-400 flex items-center gap-1">
                                    <Check className="w-3 h-3" />
                                    認証済み
                                </p>
                            </div>
                        ) : (
                            <>
                                <button
                                    onClick={handleDriveAuth}
                                    className="w-full flex items-center justify-center gap-2 bg-[var(--background)] hover:bg-[var(--card-hover)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm transition-colors"
                                >
                                    <CloudOff className="w-4 h-4" />
                                    認証する
                                </button>
                                <p className="text-xs mt-2 text-[var(--muted)]">
                                    {driveStatus?.message || '未認証'}
                                </p>
                            </>
                        )}
                        {syncResult && (
                            <p className="text-xs mt-2 text-blue-400">
                                {syncResult}
                            </p>
                        )}
                    </div>

                    {/* Classic Upload (Legacy Button, kept for fallback) */}
                    <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)] hidden">
                        <label className="block text-sm font-medium mb-2">旧ファイルアップロード</label>
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            accept=".pdf,.md,.txt,.docx"
                            onChange={handleFileUpload}
                            className="hidden"
                        />
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            disabled={isUploading}
                            className="w-full flex items-center justify-center gap-2 bg-[var(--background)] hover:bg-[var(--card-hover)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm transition-colors disabled:opacity-50"
                        >
                            {isUploading ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                                <Upload className="w-4 h-4" />
                            )}
                            {isUploading ? 'アップロード中...' : 'ファイルを選択'}
                        </button>
                        {uploadResult && (
                            <p className="text-xs mt-2 text-green-400 flex items-center gap-1">
                                <Check className="w-3 h-3" />
                                {uploadResult}
                            </p>
                        )}
                    </div>

                    {/* Reindex */}
                    <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)]">
                        <label className="block text-sm font-medium mb-2">インデックス</label>
                        <button
                            onClick={handleReindex}
                            disabled={isIndexing}
                            className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 rounded-lg px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50"
                        >
                            <RefreshCw className={`w-4 h-4 ${isIndexing ? 'animate-spin' : ''}`} />
                            {isIndexing ? '更新中...' : '再構築'}
                        </button>
                        {stats && (
                            <p className="text-xs mt-2 text-[var(--muted)]">
                                最終更新: {stats.last_updated?.split('T')[0] || '未実行'}
                            </p>
                        )}
                    </div>

                    {/* Examples */}
                    <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)]">
                        <label className="block text-sm font-medium mb-2">💡 質問例</label>
                        <div className="space-y-2">
                            {EXAMPLE_QUESTIONS.map((q, i) => (
                                <button
                                    key={i}
                                    onClick={() => handleExampleClick(q)}
                                    className="w-full text-left text-xs text-[var(--muted)] hover:text-[var(--foreground)] bg-[var(--background)] hover:bg-[var(--card-hover)] rounded-lg px-3 py-2 transition-colors line-clamp-2"
                                >
                                    {q}
                                </button>
                            ))}
                        </div>
                    </div>
                </aside >

                {/* Chat Area */}
                < div className="flex-1 flex flex-col bg-[var(--card)] rounded-xl border border-[var(--border)] overflow-hidden relative" >
                    {/* Tabs */}
                    < div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--border)] bg-[var(--muted)]/5" >
                        <button
                            onClick={() => setActiveTab('chat')}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeTab === 'chat' ? 'bg-white shadow-sm text-primary-600' : 'text-[var(--muted)] hover:bg-[var(--card-hover)]'}`}
                        >
                            <MessageSquare className="w-4 h-4" />
                            Chat
                        </button>
                        <button
                            onClick={() => setActiveTab('library')}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeTab === 'library' ? 'bg-white shadow-sm text-primary-600' : 'text-[var(--muted)] hover:bg-[var(--card-hover)]'}`}
                        >
                            <LibraryIcon className="w-4 h-4" />
                            Library
                        </button>
                    </div >

                    {/* Chat Container (Split View) */}
                    < div className="flex-1 flex overflow-hidden" style={{ display: activeTab === 'chat' ? 'flex' : 'none' }
                    }>
                        {/* Left Pane: Chat */}
                        < div className={`flex flex-col border-r border-[var(--border)] transition-all duration-300 h-full ${isPdfOpen ? 'w-1/2' : 'w-full'}`}>
                            {/* Messages */}
                            < div className="flex-1 overflow-y-auto p-4 space-y-4" >
                                {
                                    messages.length === 0 && (
                                        <div className="h-full flex flex-col items-center justify-center text-center text-[var(--muted)]">
                                            <Building2 className="w-16 h-16 mb-4 opacity-50" />
                                            <h2 className="text-lg font-medium mb-2">建築意匠ナレッジベース</h2>
                                            <p className="text-sm max-w-md">
                                                図面・カタログ・技術基準を横断検索し、
                                                建築技術に関する質問に回答します。
                                            </p>
                                        </div>
                                    )
                                }

                                {
                                    messages.map((msg, i) => (
                                        <div
                                            key={i}
                                            className={`animate-fade-in ${msg.role === 'user' ? 'flex justify-end' : ''
                                                }`}
                                        >
                                            <div
                                                className={`max-w-[85%] rounded-xl p-4 ${msg.role === 'user'
                                                    ? 'bg-primary-600 text-white'
                                                    : 'bg-[var(--background)]'
                                                    }`}
                                            >
                                                {msg.role === 'user' ? (
                                                    <p>{msg.content}</p>
                                                ) : (
                                                    <div className="markdown-content">
                                                        <ReactMarkdown
                                                            components={{
                                                                p: ({ children }) => {
                                                                    const currentSources = msg.sources || [];
                                                                    const transformed = React.Children.map(children, (child) => {
                                                                        if (typeof child === 'string') {
                                                                            return transformCitations(
                                                                                child,
                                                                                currentSources,
                                                                                (url, page) => {
                                                                                    setPdfUrl(url);
                                                                                    setPdfInitialPage(page);
                                                                                    setIsPdfOpen(true);
                                                                                }
                                                                            );
                                                                        }
                                                                        return child;
                                                                    });
                                                                    return <p>{transformed}</p>;
                                                                },
                                                            }}
                                                        >{msg.content}</ReactMarkdown>
                                                    </div>
                                                )}

                                                {msg.sources && msg.sources.length > 0 && (
                                                    <div className="mt-4 pt-3 border-t border-[var(--border)]">
                                                        <p className="text-xs text-[var(--muted)] mb-2 font-medium">参照ファイル:</p>
                                                        <div className="flex flex-wrap gap-2">
                                                            {msg.sources.map((src, j) => (
                                                                <SourceCard
                                                                    key={j}
                                                                    src={src}
                                                                    onPageClick={(url, page) => {
                                                                        setPdfUrl(url);
                                                                        setPdfInitialPage(page);
                                                                        setIsPdfOpen(true);
                                                                    }}
                                                                />
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ))
                                }

                                {
                                    isLoading && (
                                        <div className="animate-fade-in">
                                            <div className="max-w-[85%] rounded-xl p-4 bg-[var(--background)]">
                                                <div className="flex items-center gap-2 text-[var(--muted)]">
                                                    <Loader2 className="w-4 h-4 animate-spin" />
                                                    <span className="loading-dots">回答を生成中</span>
                                                </div>
                                            </div>
                                        </div>
                                    )
                                }

                                <div ref={messagesEndRef} />
                            </div >

                            {/* Input area */}
                            <div className="border-t border-[var(--border)] p-4 space-y-3">
                                {/* Context Sheet Panel — outside <form> to avoid accidental submission */}
                                <ContextSheetPanel
                                    availableModels={availableModels}
                                    availableRoles={availableRoles}
                                    activeContextSheet={activeContextSheet}
                                    activeSheetTitle={activeSheetTitle}
                                    activeContextRole={activeContextRole}
                                    onSheetApplied={handleSheetApplied}
                                    onSheetCleared={() => { setActiveContextSheet(null); setActiveSheetTitle(null); setActiveContextRole(null); }}
                                    onStreamStart={handleSheetStreamStart}
                                    onStreamChunk={handleSheetStreamChunk}
                                    onStreamEnd={handleSheetStreamEnd}
                                    isStreaming={isGeneratingSheet}
                                />

                                {/* Controls row */}
                                <div className="flex flex-col gap-3">
                                    <div className="flex flex-wrap items-center justify-between gap-y-2 gap-x-4">
                                        <div className="flex flex-wrap items-center gap-2 flex-1">
                                            {/* Model Selector */}
                                            <div className="flex items-center gap-1.5">
                                                <span className="text-xs text-[var(--muted)] flex-shrink-0">🤖 モデル:</span>
                                                <div className="relative min-w-[150px] max-w-[220px]">
                                                    <select
                                                        value={selectedModel}
                                                        onChange={(e) => setSelectedModel(e.target.value)}
                                                        className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-2 py-1 text-xs appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary-500 pr-6"
                                                    >
                                                        {Object.keys(availableModels).length > 0
                                                            ? Object.entries(availableModels).map(([k, v]) => (
                                                                <option key={k} value={k}>{v}</option>
                                                            ))
                                                            : (
                                                                <>
                                                                    <option value="gemini-3-flash-preview">Gemini 3 Flash（高速・標準）</option>
                                                                    <option value="gemini-3.1-pro-preview">Gemini 3.1 Pro（高精度）</option>
                                                                    <option value="gemini-2.0-flash">Gemini 2.0 Flash（安定板）</option>
                                                                </>
                                                            )
                                                        }
                                                    </select>
                                                    <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--muted)] pointer-events-none" />
                                                </div>
                                            </div>

                                            {/* RAG Toggle */}
                                            <div className="flex items-center gap-1.5 border-l border-[var(--border)] pl-2">
                                                <button
                                                    type="button"
                                                    onClick={() => setUseRag(prev => !prev)}
                                                    className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-all font-medium ${useRag
                                                        ? 'bg-primary-50 border-primary-300 text-primary-700 hover:bg-primary-100'
                                                        : 'bg-[var(--card)] border-[var(--border)] text-[var(--muted)] hover:bg-[var(--card-hover)]'
                                                        }`}
                                                    title={useRag ? '知識ベース参照中（クリックでOFF）' : '直接回答モード（クリックでON）'}
                                                >
                                                    <span>{useRag ? '📚' : '💬'}</span>
                                                    <span>{useRag ? 'RAG ON' : 'RAG OFF'}</span>
                                                </button>
                                                <span className="text-[10px] text-[var(--muted)] hidden sm:inline-block">
                                                    {useRag ? '参照する' : '参照しない'}
                                                </span>
                                            </div>

                                            {activeContextSheet && (
                                                <span className="text-[10px] px-2 py-1 rounded-full bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center gap-1 flex-shrink-0">
                                                    <Sparkles className="w-2.5 h-2.5" />
                                                    {activeSheetTitle || 'コンテキスト適用中'}
                                                </span>
                                            )}
                                        </div>

                                        {/* New Chat Button */}
                                        <button
                                            onClick={async () => {
                                                try {
                                                    const newSession = await createSession();
                                                    setActiveSessionId(newSession.id);
                                                    setMessages([]);
                                                    fetchSessions().then(setSessions);
                                                } catch (err) {
                                                    console.error(err);
                                                }
                                            }}
                                            className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--card)] shadow-sm hover:bg-primary-50 flex items-center gap-1.5 text-primary-600 font-medium transition-all flex-shrink-0"
                                            title="新しい会話を始める"
                                        >
                                            <MessageSquare className="w-4 h-4" />
                                            新規チャット
                                        </button>
                                    </div>
                                </div>

                                {/* Main chat input */}
                                <form onSubmit={handleSubmit} className="flex gap-2">
                                    <input
                                        type="text"
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        placeholder="質問を入力してください..."
                                        className="flex-1 bg-[var(--background)] border border-[var(--border)] rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary-500 placeholder:text-[var(--muted)]"
                                        disabled={isLoading}
                                    />
                                    <button
                                        type="submit"
                                        disabled={isLoading || !input.trim()}
                                        className="bg-gradient-to-r from-primary-500 to-accent-500 hover:from-primary-600 hover:to-accent-600 rounded-xl px-6 py-3 font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <Send className="w-5 h-5" />
                                    </button>
                                </form>
                            </div>

                        </div >

                        {/* Right Pane: PDF Viewer */}
                        {
                            isPdfOpen && (
                                <div className="w-1/2 h-full border-l border-[var(--border)] relative transition-all duration-300">
                                    <PDFViewer
                                        url={pdfUrl}
                                        initialPage={pdfInitialPage}
                                        onClose={() => setIsPdfOpen(false)}
                                    />
                                </div>
                            )
                        }
                    </div >

                    {/* Library Container */}
                    {
                        activeTab === 'library' && (
                            <div className="flex-1 overflow-hidden p-4 h-full">
                                <Library />
                            </div>
                        )
                    }
                </div >
            </div >
        </div >
    );
}
