'use client';

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
    MessageSquare
} from 'lucide-react';
import Library from './components/Library';

interface Message {
    role: 'user' | 'assistant';
    content: string;
    sources?: SourceFile[];
}

interface SourceFile {
    filename: string;
    category: string;
    relevance_count: number;
    source_pdf?: string;
    pages?: number[]; // 追加: ページ番号リスト
}



interface Stats {
    file_count: number;
    chunk_count: number;
    last_updated: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const EXAMPLE_QUESTIONS = [
    'ALCとECPの防水性能・コスト・メンテナンス性の違いを比較して',
    'S造事務所の外壁矩計図で確認すべきポイントは？',
    'サッシの気密・水密・耐風圧等級の選定基準を教えて',
    'シーリングの種類と使い分け',
    '屋根防水でアスファルト防水と塩ビシート防水の比較',
];

const CATEGORIES = [
    { value: '', label: '全て（横断検索）' },
    { value: '01_カタログ', label: '01_カタログ' },
    { value: '02_図面', label: '02_図面' },
    { value: '03_技術基準', label: '03_技術基準' },
    { value: '04_リサーチ成果物', label: '04_リサーチ成果物' },
    { value: 'uploads', label: 'アップロード' },
];

export default function Home() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [category, setCategory] = useState('');
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
    const [isPdfOpen, setIsPdfOpen] = useState(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const fetchStats = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/stats`);
            if (res.ok) {
                const data = await res.json();
                setStats(data);
            }
        } catch (error) {
            console.error('Stats fetch error:', error);
        }
    }, []);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('auth') === 'success') {
            alert('認証が完了しました！');
            window.history.replaceState(null, '', window.location.pathname);
        }

        fetchStats();
        checkDriveStatus();
    }, [fetchStats]);

    const checkDriveStatus = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/drive/status`);
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
            const res = await fetch(`${API_BASE}/api/drive/auth`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.auth_url) {
                    window.location.href = data.auth_url;
                }
            } else {
                console.error('Auth request failed');
                alert('認証URLの取得に失敗しました');
            }
        } catch (error) {
            console.error('Drive auth error:', error);
            alert('接続エラー');
        }
    };

    const handleDriveSync = async () => {
        setIsSyncing(true);
        setSyncResult(null);
        try {
            const res = await fetch(`${API_BASE}/api/drive/sync`, {
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
            const res = await fetch(`${API_BASE}/api/sync-drive`, { method: 'POST' });
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
        setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
        setIsLoading(true);

        try {
            const res = await fetch(`${API_BASE}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: userMessage,
                    category: category || null,
                }),
            });

            if (!res.ok) throw new Error('API error');

            const data = await res.json();
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: data.answer,
                sources: data.sources,
            }]);
        } catch (error) {
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: 'エラーが発生しました。もう一度お試しください。',
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleExampleClick = (question: string) => {
        setInput(question);
    };

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
            const res = await fetch(`${API_BASE}/api/upload/multiple`, {
                method: 'POST',
                body: formData,
            });

            if (res.ok) {
                const data = await res.json();
                setUploadResult(`${data.uploaded.length}ファイルをアップロードしました`);
                fetchStats();

                // チャット履歴に案内メッセージを追加
                const filenames = data.uploaded.map((f: any) => f.filename).join(', ');
                const isPdf = filenames.toLowerCase().includes('.pdf');

                const message = `${data.uploaded.length}個のファイル（${filenames}）を受け付けました。\n\n` +
                    (isPdf
                        ? "これよりバックグラウンドでテキスト抽出（OCR）を開始します。この処理には時間がかかる場合があります。\n\n【次のステップ】\n1. 「Library」タブでステータスを確認\n2. ステータスが完了になったら、左の「🔄 再構築」ボタンをクリック\n3. これで最新の知識としてチャットで利用可能になります。"
                        : "【次のステップ】\n左の「🔄 再構築」ボタンをクリックしてください。\nこれでチャットの知識ベースに追加されます。");

                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: message,
                }]);
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
            const res = await fetch(`${API_BASE}/api/index`, { method: 'POST' });
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
                <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
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
            <main className="flex-1 max-w-6xl mx-auto w-full flex flex-col md:flex-row gap-4 p-4">
                {/* Sidebar */}
                <aside className="md:w-64 space-y-4">
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

                    {/* Upload */}
                    <div className="bg-[var(--card)] rounded-xl p-4 border border-[var(--border)]">
                        <label className="block text-sm font-medium mb-2">ファイルアップロード</label>
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
                </aside>

                {/* Chat Area */}
                <div className="flex-1 flex flex-col bg-[var(--card)] rounded-xl border border-[var(--border)] overflow-hidden relative">
                    {/* Tabs */}
                    <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--border)] bg-[var(--muted)]/5">
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
                    </div>

                    {/* Chat Container (Split View) */}
                    <div className="flex-1 flex overflow-hidden" style={{ display: activeTab === 'chat' ? 'flex' : 'none' }}>
                        {/* Left Pane: Chat */}
                        <div className={`flex flex-col border-r border-[var(--border)] transition-all duration-300 h-full ${isPdfOpen ? 'w-1/2' : 'w-full'}`}>
                            {/* Messages */}
                            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                                {messages.length === 0 && (
                                    <div className="h-full flex flex-col items-center justify-center text-center text-[var(--muted)]">
                                        <Building2 className="w-16 h-16 mb-4 opacity-50" />
                                        <h2 className="text-lg font-medium mb-2">建築意匠ナレッジベース</h2>
                                        <p className="text-sm max-w-md">
                                            図面・カタログ・技術基準を横断検索し、
                                            建築技術に関する質問に回答します。
                                        </p>
                                    </div>
                                )}

                                {messages.map((msg, i) => (
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
                                                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                                                </div>
                                            )}

                                            {msg.sources && msg.sources.length > 0 && (
                                                <div className="mt-4 pt-3 border-t border-[var(--border)]">
                                                    <p className="text-xs text-[var(--muted)] mb-2 font-medium">参照ファイル:</p>
                                                    <div className="flex flex-wrap gap-2">
                                                        {msg.sources.map((src, j) => (
                                                            <div
                                                                key={j}
                                                                className="flex items-center gap-2 bg-[var(--card)] border border-[var(--border)] px-2 py-1.5 rounded-md"
                                                            >
                                                                <span className="text-xs flex items-center gap-1">
                                                                    <FileText className="w-3 h-3 text-primary-500" />
                                                                    {src.filename}
                                                                </span>
                                                                {src.source_pdf && (
                                                                    <a
                                                                        href={`${API_BASE}/api/files/view/${src.source_pdf}`}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        className="text-xs text-blue-500 hover:text-blue-600 hover:underline flex items-center gap-0.5 ml-1 border-l border-[var(--border)] pl-2"
                                                                        title="PDFを開く"
                                                                    >
                                                                        <ExternalLink className="w-3 h-3" />
                                                                        PDF
                                                                    </a>
                                                                )}
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}

                                {isLoading && (
                                    <div className="animate-fade-in">
                                        <div className="max-w-[85%] rounded-xl p-4 bg-[var(--background)]">
                                            <div className="flex items-center gap-2 text-[var(--muted)]">
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                <span className="loading-dots">回答を生成中</span>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                <div ref={messagesEndRef} />
                            </div>

                            {/* Input */}
                            <form onSubmit={handleSubmit} className="border-t border-[var(--border)] p-4">
                                <div className="flex gap-2">
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
                                </div>
                            </form>
                        </div>

                        {/* Right Pane: PDF Viewer */}
                        {isPdfOpen && (
                            <div className="w-1/2 flex flex-col bg-gray-100 border-l border-[var(--border)] relative h-full">
                                <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-[var(--border)]">
                                    <span className="text-sm font-medium text-gray-700 truncate max-w-[300px]">
                                        {pdfUrl?.split('/').pop()?.split('#')[0] || 'PDF Viewer'}
                                    </span>
                                    <button
                                        onClick={() => setIsPdfOpen(false)}
                                        className="p-1 hover:bg-gray-100 rounded-full text-gray-500"
                                    >
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>
                                <div className="flex-1 relative">
                                    {pdfUrl ? (
                                        <iframe
                                            src={pdfUrl}
                                            className="absolute inset-0 w-full h-full border-none"
                                            title="PDF Viewer"
                                        />
                                    ) : (
                                        <div className="flex items-center justify-center h-full text-gray-400">
                                            <p>PDFを選択してください</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Library Container */}
                    {activeTab === 'library' && (
                        <div className="flex-1 overflow-hidden p-4 h-full">
                            <Library />
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
