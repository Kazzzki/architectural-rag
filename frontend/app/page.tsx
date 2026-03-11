'use client';

import React, { useState, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import { 
    Send, 
    Loader2, 
    Plus, 
    BookOpen, 
    MessageSquare, 
    ExternalLink, 
    FileText, 
    Library as LibraryIcon,
    ChevronDown,
    Building2,
    Sparkles,
    Database,
    Globe
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { 
    SourceFile, 
    StreamUpdate, 
    fetchSessions as apiFetchSessions, 
    fetchModels as apiFetchModels,
    createSession as apiCreateSession,
    fetchSessionDetail as apiFetchSessionDetail,
    saveMessages as apiSaveMessages
} from '../lib/api';
import SourceCard from './components/SourceCard';
const PDFViewer = dynamic(() => import('./components/PDFViewer'), { ssr: false });
import Library from './components/Library';

// --- Citation Logic ---
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
    if (!src) return <span>[{sourceId}:p.{page}]</span>;

    const url = src.source_pdf ? `/api/pdf/${src.source_pdf}` : null;
    if (!url) {
        return (
            <span className="inline-flex items-center text-[11px] px-1.5 py-0.5 mx-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100 font-mono">
                {sourceId} p.{page}
            </span>
        );
    }

    return (
        <button
            onClick={() => onPageClick(url, page)}
            className="inline-flex items-center text-[11px] px-1.5 py-0.5 mx-0.5 rounded bg-blue-100 text-blue-700 border border-blue-200 hover:bg-blue-200 transition-colors cursor-pointer font-mono"
            title={`${src.source_pdf_name || src.filename} p.${page} を開く`}
        >
            {sourceId} p.{page}
        </button>
    );
}

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

interface Message {
    role: 'user' | 'assistant';
    content: string;
    sources?: SourceFile[];
    webSources?: { title: string; url: string }[];
}

interface Session {
    id: string;
    title: string | null;
    updated_at: string;
}

export default function Home() {
    // State
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [sessions, setSessions] = useState<Session[]>([]);
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'chat' | 'library'>('chat');
    const [useRag, setUseRag] = useState(true);
    const [useWebSearch, setUseWebSearch] = useState(false);
    const [selectedModel, setSelectedModel] = useState('gemini-2.0-flash');
    const [availableModels, setAvailableModels] = useState<Record<string, string>>({});
    
    // PDF Viewer State
    const [isPdfOpen, setIsPdfOpen] = useState(false);
    const [pdfUrl, setPdfUrl] = useState<string | null>(null);
    const [pdfInitialPage, setPdfInitialPage] = useState<number | undefined>(undefined);
    
    // UI state
    const [activeLayerB, setActiveLayerB] = useState<string | null>(null);
    
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);
    const lastRequestIdRef = useRef<number>(0);

    // Initial load
    useEffect(() => {
        fetchSessions().then(setSessions);
        fetchModels();
    }, []);

    // Scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const fetchSessions = async () => {
        try {
            return await apiFetchSessions();
        } catch (err) {
            console.error(err);
            return [];
        }
    };

    const fetchModels = async () => {
        try {
            const data = await apiFetchModels();
            setAvailableModels(data);
        } catch (err) {
            console.error(err);
        }
    };

    const createSession = async () => {
        return await apiCreateSession();
    };

    const loadSession = async (id: string) => {
        try {
            setActiveSessionId(id);
            const data = await apiFetchSessionDetail(id);
            const msgs = data.messages || [];
            setMessages(msgs.map((m: any) => ({
                role: m.role,
                content: m.content,
                sources: m.sources,
                webSources: m.web_sources
            })));
        } catch (err) {
            console.error(err);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        const userMessageContent = input.trim();
        setInput('');
        
        // --- Snapshot history BEFORE adding new message ---
        const historySnapshot = [...messages];
        
        // Add user message to UI
        setMessages(prev => [...prev, { role: 'user', content: userMessageContent }]);

        // Add placeholder assistant message
        setMessages(prev => [...prev, { role: 'assistant', content: '', sources: undefined, webSources: undefined }]);

        setIsLoading(true);

        // Cancel previous request
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const abortController = new AbortController();
        abortControllerRef.current = abortController;
        const requestId = ++lastRequestIdRef.current;

        try {
            const { chatStream, saveMessages } = await import('../lib/api');
            let accumulatedAnswer = '';
            let currentSources: SourceFile[] = [];
            let currentWebSources: { title: string; url: string }[] = [];

            for await (const update of chatStream({
                session_id: activeSessionId || undefined,
                question: userMessageContent,
                model: selectedModel,
                use_rag: useRag,
                use_web_search: useWebSearch,
                history: historySnapshot.length > 0 ? historySnapshot : undefined,
                signal: abortController.signal
            })) {
                if (requestId !== lastRequestIdRef.current) break;

                if (update.type === 'answer') {
                    accumulatedAnswer += update.data;
                    setMessages(prev => {
                        const next = [...prev];
                        const last = next[next.length - 1];
                        if (last.role === 'assistant') last.content = accumulatedAnswer;
                        return next;
                    });
                } else if (update.type === 'sources') {
                    currentSources = update.data;
                    setMessages(prev => {
                        const next = [...prev];
                        const last = next[next.length - 1];
                        if (last.role === 'assistant') last.sources = currentSources;
                        return next;
                    });
                } else if (update.type === 'web_sources') {
                    currentWebSources = update.data;
                    setMessages(prev => {
                        const next = [...prev];
                        const last = next[next.length - 1];
                        if (last.role === 'assistant') last.webSources = currentWebSources;
                        return next;
                    });
                } else if (update.type === 'error') {
                    throw new Error(update.data);
                }
            }

            // Persistence
            let sessionIdToSave = activeSessionId;
            if (!sessionIdToSave) {
                const session = await createSession();
                sessionIdToSave = session.id;
                setActiveSessionId(session.id);
            }

            if (sessionIdToSave) {
                await apiSaveMessages(sessionIdToSave, {
                    user: userMessageContent,
                    assistant: accumulatedAnswer,
                    sources: currentSources,
                    web_sources: currentWebSources,
                    model: selectedModel
                });
            }
            fetchSessions().then(setSessions);

        } catch (err: any) {
            if (err.name === 'AbortError') return;
            console.error(err);
            setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last.role === 'assistant') last.content = `Error: ${err.message}`;
                return next;
            });
        } finally {
            setIsLoading(false);
            abortControllerRef.current = null;
        }
    };

    return (
        <div className="flex h-screen bg-[var(--background)] text-[var(--foreground)] overflow-hidden font-sans">
            {/* Sidebar */}
            <div className="w-64 border-r border-[var(--border)] bg-[var(--card)] flex flex-col shrink-0">
                <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
                    <Building2 className="w-6 h-6 text-primary-500" />
                    <h1 className="font-bold text-lg tracking-tight">Antigravity</h1>
                </div>

                <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
                    <button
                        onClick={() => {
                            setActiveSessionId(null);
                            setMessages([]);
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[var(--card-hover)] transition-colors text-sm font-medium mb-4 border border-[var(--border)] shadow-sm"
                    >
                        <Plus className="w-4 h-4" /> 新規チャット
                    </button>

                    <div className="px-3 mb-2">
                        <p className="text-[10px] font-bold text-[var(--muted)] uppercase tracking-wider">最近のチャット</p>
                    </div>

                    {sessions.map(s => (
                        <button
                            key={s.id}
                            onClick={() => loadSession(s.id)}
                            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all truncate hover:bg-[var(--card-hover)] ${activeSessionId === s.id ? 'bg-primary-50 text-primary-700 font-medium border border-primary-200' : 'text-[var(--foreground)]'}`}
                        >
                            {s.title || `新規チャット (${s.id.slice(0, 8)})`}
                        </button>
                    ))}
                </div>

                <div className="p-4 border-t border-[var(--border)]">
                    <button 
                        onClick={() => setActiveTab(activeTab === 'chat' ? 'library' : 'chat')}
                        className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)] text-sm hover:bg-[var(--card-hover)] transition-colors shadow-sm"
                    >
                        <div className="flex items-center gap-2">
                            {activeTab === 'chat' ? <LibraryIcon className="w-4 h-4" /> : <MessageSquare className="w-4 h-4" />}
                            <span>{activeTab === 'chat' ? 'ライブラリ' : 'チャットに戻る'}</span>
                        </div>
                    </button>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0 bg-[#fbfbfb]">
                {activeTab === 'chat' ? (
                    <div className="flex-1 flex min-h-0">
                        {/* Chat Area */}
                        <div className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ${isPdfOpen ? 'w-1/2' : 'w-full'}`}>
                            {/* Messages Container */}
                            <div className="flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar">
                                {messages.length === 0 && (
                                    <div className="h-full flex flex-col items-center justify-center text-[var(--muted)] opacity-60">
                                        <Building2 className="w-16 h-16 mb-4" />
                                        <h2 className="text-xl font-semibold mb-2">建築設計ナレッジ検索</h2>
                                        <p className="max-w-md text-center text-sm">設計基準やカタログを横断的に検索し、高度な技術回答を生成します。</p>
                                    </div>
                                )}

                                {messages.map((msg, i) => (
                                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2`}>
                                        <div className={`max-w-[85%] rounded-2xl p-4 shadow-sm ${msg.role === 'user' ? 'bg-primary-600 text-white rounded-tr-none' : 'bg-white border border-[var(--border)] rounded-tl-none'}`}>
                                            <div className="markdown-content text-sm leading-relaxed overflow-x-auto">
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

                                            {/* RAG Sources */}
                                            {msg.sources && msg.sources.length > 0 && (
                                                <div className="mt-4 pt-3 border-t border-[var(--border)]">
                                                    <p className="text-[10px] font-bold text-[var(--muted)] mb-2 uppercase tracking-tighter">参照資料</p>
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

                                            {/* Web Sources */}
                                            {msg.webSources && msg.webSources.length > 0 && (
                                                <div className="mt-4 pt-3 border-t border-[var(--border)]">                                                     <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                         {msg.webSources.map((ws, j) => (
                                                             <a 
                                                                 key={j} 
                                                                 href={ws.url} 
                                                                 target="_blank" 
                                                                 rel="noopener noreferrer"
                                                                 className="flex items-center gap-2.5 p-2 rounded-xl bg-blue-50/50 border border-blue-100/50 text-[11px] text-blue-700 hover:bg-blue-100 hover:border-blue-200 transition-all group shadow-sm active:scale-[0.98]"
                                                             >
                                                                 <div className="p-1.5 rounded-lg bg-blue-100/50 group-hover:bg-blue-200/50 transition-colors">
                                                                     <Globe className="w-3.5 h-3.5 flex-shrink-0 text-blue-600" />
                                                                 </div>
                                                                 <div className="flex-1 min-w-0">
                                                                     <p className="font-semibold truncate leading-tight">{ws.title || ws.url}</p>
                                                                     <p className="text-[10px] text-blue-500/80 truncate mt-0.5">{new URL(ws.url).hostname}</p>
                                                                 </div>
                                                                 <ExternalLink className="w-2.5 h-2.5 opacity-40 group-hover:opacity-100 flex-shrink-0 transition-opacity" />
                                                             </a>
                                                         ))}
                                                     </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                
                                {isLoading && (
                                    <div className="flex justify-start animate-pulse">
                                        <div className="bg-white border border-[var(--border)] rounded-2xl p-4 rounded-tl-none flex items-center gap-3">
                                            <Loader2 className="w-4 h-4 animate-spin text-primary-500" />
                                            <span className="text-sm text-[var(--muted)]">
                                                {useWebSearch ? 'ウェブ検索中...' : '考案中...'}
                                            </span>
                                        </div>
                                    </div>
                                )}
                                <div ref={messagesEndRef} />
                            </div>

                            {/* Input Area */}
                            <div className="p-4 bg-white border-t border-[var(--border)]">
                                <form onSubmit={handleSubmit} className="relative max-w-4xl mx-auto">
                                    <div className="flex items-center gap-2 mb-3">
                                        {/* Model Select */}
                                        <div className="relative">
                                            <select 
                                                value={selectedModel}
                                                onChange={(e) => setSelectedModel(e.target.value)}
                                                className="appearance-none bg-[var(--background)] border border-[var(--border)] rounded-full px-4 py-1.5 pr-8 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-primary-400 hover:bg-[var(--card-hover)] transition-colors cursor-pointer"
                                            >
                                                 <option value="gemini-3.1-flash-lite">Gemini 3.1 Flash Lite</option>
                                                 <option value="gemini-3-flash-preview">Gemini 3 Flash</option>
                                                 <option value="gemini-3.1-pro-preview">Gemini 3.1 Pro</option>
                                                 <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>
                                            </select>
                                            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--muted)] pointer-events-none" />
                                        </div>

                                        {/* RAG Toggle */}
                                        <button
                                            type="button"
                                            onClick={() => setUseRag(!useRag)}
                                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-all border ${useRag ? 'bg-primary-50 border-primary-200 text-primary-700' : 'bg-gray-50 border-gray-200 text-gray-500 hover:bg-gray-100'}`}
                                        >
                                            <Database className="w-3.5 h-3.5" />
                                            RAG {useRag ? 'ON' : 'OFF'}
                                        </button>

                                        {/* Web Toggle */}
                                        <button
                                            type="button"
                                            onClick={() => setUseWebSearch(!useWebSearch)}
                                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-all border ${useWebSearch ? 'bg-blue-50 border-blue-200 text-blue-700 shadow-sm' : 'bg-gray-50 border-gray-200 text-gray-500 hover:bg-gray-100'}`}
                                        >
                                            <Globe className="w-3.5 h-3.5" />
                                            ウェブ検索 {useWebSearch ? 'ON' : 'OFF'}
                                        </button>
                                    </div>

                                    <div className="relative flex items-end gap-2 bg-[var(--background)] border border-[var(--border)] rounded-2xl p-2 focus-within:ring-2 focus-within:ring-primary-400 focus-within:border-primary-400 transition-all shadow-sm">
                                        <textarea
                                            value={input}
                                            onChange={(e) => setInput(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter' && !e.shiftKey) {
                                                    e.preventDefault();
                                                    handleSubmit(e as any);
                                                }
                                            }}
                                            placeholder="メッセージを入力..."
                                            rows={1}
                                            className="flex-1 max-h-48 resize-none bg-transparent border-none focus:ring-0 p-2 text-sm custom-scrollbar"
                                            style={{ height: 'auto', minHeight: '40px' }}
                                        />
                                        <button
                                            type="submit"
                                            disabled={!input.trim() || isLoading}
                                            className="bg-primary-600 hover:bg-primary-700 text-white p-2 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md active:scale-95"
                                        >
                                            {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                                        </button>
                                    </div>
                                </form>
                            </div>
                        </div>

                        {/* PDF Viewer Pane */}
                        {isPdfOpen && (
                            <div className="w-1/2 h-full border-l border-[var(--border)] bg-white animate-in slide-in-from-right duration-300">
                                <PDFViewer
                                    url={pdfUrl!}
                                    initialPage={pdfInitialPage}
                                    onClose={() => setIsPdfOpen(false)}
                                />
                            </div>
                        )}
                    </div>
                ) : (
                    <Library />
                )}
            </div>

            {/* Global Styles */}
            <style jsx global>{`
                :root {
                    --primary-50: #eff6ff;
                    --primary-200: #bfdbfe;
                    --primary-500: #3b82f6;
                    --primary-600: #2563eb;
                    --primary-700: #1d4ed8;
                    --background: #fdfdfd;
                    --foreground: #1e293b;
                    --card: #ffffff;
                    --card-hover: #f8fafc;
                    --border: #e2e8f0;
                    --muted: #64748b;
                }

                .markdown-content p { margin-bottom: 0.75rem; }
                .markdown-content p:last-child { margin-bottom: 0; }
                .markdown-content ul, .markdown-content ol { margin-bottom: 0.75rem; padding-left: 1.5rem; }
                .markdown-content li { margin-bottom: 0.25rem; }
                .markdown-content strong { font-weight: 600; }
                .markdown-content code { background: #f1f5f9; padding: 0.1rem 0.3rem; border-radius: 0.25rem; font-family: monospace; }
                
                .custom-scrollbar::-webkit-scrollbar { width: 5px; }
                .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
                .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 5px; }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
            `}</style>
        </div>
    );
}
