import React, { useState, useEffect, useRef } from 'react';
import { Send, FileText, Link as LinkIcon, MessageSquare, BookOpen, Loader2, GripVertical } from 'lucide-react';

import ReactMarkdown from 'react-markdown';

interface KnowledgeItem {
    id: string;
    source: string;
    content: string;
    relevance: number;
    full_content: string;
}

interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
}

interface IntegratedSidebarProps {
    selectedNode: any | null; // ProcessNode
    knowledge: KnowledgeItem[];
    chatHistory: ChatMessage[];
    isSearching: boolean;
    onChatSend: (message: string) => void;
    onDragStart: (event: React.DragEvent, item: KnowledgeItem) => void;
}

export default function IntegratedSidebar({
    selectedNode,
    knowledge,
    chatHistory,
    isSearching,
    onChatSend,
    onDragStart
}: IntegratedSidebarProps) {
    const [prompt, setPrompt] = useState("");
    const [splitRatio, setSplitRatio] = useState(50); // percentage for top panel
    const draggingRef = useRef(false);

    // Auto-scroll chat
    const chatEndRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [chatHistory]);

    if (!selectedNode) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-[var(--muted)] text-center">
                <MessageSquare className="w-12 h-12 mb-4 opacity-20" />
                <p>ノードを選択すると<br />AIチャットと関連知識が表示されます</p>
            </div>
        );
    }

    const handleSend = () => {
        if (!prompt.trim()) return;
        onChatSend(prompt);
        setPrompt("");
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleDragMove = (e: MouseEvent) => {
        if (!draggingRef.current) return;
        const containerHeight = document.getElementById('sidebar-container')?.clientHeight || 1;
        // Calculate percentage relative to container top (offset)
        const parentTop = document.getElementById('sidebar-container')?.getBoundingClientRect().top || 0;
        const relativeY = e.clientY - parentTop;
        const ratio = Math.min(Math.max((relativeY / containerHeight) * 100, 20), 80);
        setSplitRatio(ratio);
    };

    const handleDragUp = () => {
        draggingRef.current = false;
        document.removeEventListener('mousemove', handleDragMove);
        document.removeEventListener('mouseup', handleDragUp);
    };

    const startResize = () => {
        draggingRef.current = true;
        document.addEventListener('mousemove', handleDragMove);
        document.addEventListener('mouseup', handleDragUp);
    };

    return (
        <div id="sidebar-container" className="flex-1 flex flex-col h-full bg-white/50 relative overflow-hidden">
            {/* Top: Chat Section */}
            <div style={{ height: `${splitRatio}%` }} className="flex flex-col min-h-0 border-b border-[var(--border)]">
                <div className="p-3 border-b border-[var(--border)] bg-gray-50 flex items-center justify-between">
                    <h3 className="text-xs font-bold text-gray-700 flex items-center gap-2">
                        <MessageSquare className="w-3.5 h-3.5" />
                        AIコンテキストチャット
                    </h3>
                    <span className="text-[10px] text-gray-400 truncate max-w-[120px]">
                        {selectedNode.label}
                    </span>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {chatHistory.length === 0 ? (
                        <div className="text-center text-xs text-gray-400 mt-4">
                            このノードについて質問してみましょう。
                        </div>
                    ) : (
                        chatHistory.map((msg, idx) => (
                            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                <div className={`max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed ${msg.role === 'user'
                                    ? 'bg-blue-500 text-white'
                                    : 'bg-white border border-gray-200 text-gray-800 shadow-sm markdown-content'
                                    }`}>
                                    {msg.role === 'user' ? (
                                        msg.content
                                    ) : (
                                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                    <div ref={chatEndRef} />
                </div>

                <div className="p-3 bg-white border-t border-[var(--border)]">
                    <div className="relative">
                        <textarea
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="AIに質問..."
                            className="w-full px-3 py-2 pr-10 text-xs bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400 resize-none h-20"
                        />
                        <button
                            onClick={handleSend}
                            disabled={!prompt.trim()}
                            className="absolute bottom-2 right-2 p-1.5 text-blue-500 hover:bg-blue-50 rounded-md disabled:text-gray-300"
                        >
                            <Send className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            </div>

            {/* Resizer Handle */}
            <div
                className="h-1.5 bg-gray-100 hover:bg-blue-100 cursor-row-resize flex items-center justify-center border-y border-[var(--border)]"
                onMouseDown={startResize}
            >
                <div className="w-8 h-1 bg-gray-300 rounded-full" />
            </div>

            {/* Bottom: Knowledge Section */}
            <div style={{ height: `${100 - splitRatio}%` }} className="flex flex-col min-h-0 bg-gray-50/50">
                <div className="p-3 border-b border-[var(--border)] flex items-center justify-between">
                    <h3 className="text-xs font-bold text-gray-700 flex items-center gap-2">
                        <BookOpen className="w-3.5 h-3.5" />
                        ナレッジ (RAG)
                    </h3>
                    {isSearching && (
                        <span className="flex items-center gap-1 text-[10px] text-blue-500">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            検索中...
                        </span>
                    )}
                </div>

                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                    {knowledge.length === 0 ? (
                        <div className="text-center text-xs text-gray-400 mt-8">
                            関連情報はまだ見つかっていません。<br />
                            ノードに入力すると自動検索されます。
                        </div>
                    ) : (
                        knowledge.map((item) => (
                            <div
                                key={item.id}
                                draggable
                                onDragStart={(e) => onDragStart(e, item)}
                                className="bg-white p-3 rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-all cursor-move group"
                            >
                                <div className="flex items-center justify-between mb-1.5">
                                    <span className="text-[10px] font-medium text-blue-600 flex items-center gap-1 bg-blue-50 px-1.5 py-0.5 rounded">
                                        <FileText className="w-3 h-3" />
                                        {item.source}
                                    </span>
                                    <GripVertical className="w-3 h-3 text-gray-300 opacity-0 group-hover:opacity-100" />
                                </div>
                                <p className="text-xs text-gray-700 leading-snug line-clamp-3">
                                    {item.content}
                                </p>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
