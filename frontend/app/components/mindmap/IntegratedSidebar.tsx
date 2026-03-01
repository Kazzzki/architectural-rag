import React, { useState, useEffect, useRef } from 'react';
import { Send, FileText, MessageSquare, BookOpen, Database, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import NodeDetailPanel from './NodeDetailPanel';
import KnowledgePanel from './KnowledgePanel';

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

interface EdgeData {
    id: string;
    source: string;
    target: string;
    type: string;
    reason: string;
}

interface IntegratedSidebarProps {
    selectedNode: any | null;
    knowledge: KnowledgeItem[];
    chatHistory: ChatMessage[];
    isSearching: boolean;
    onChatSend: (message: string) => void;
    onDragStart: (event: React.DragEvent, item: KnowledgeItem) => void;

    // New props for NodeDetailPanel integration
    incomingEdges: EdgeData[];
    outgoingEdges: EdgeData[];
    getNodeLabel: (nodeId: string) => string;
    onNavigate: (nodeId: string) => void;
    isEditMode: boolean;
    onStatusChange: (nodeId: string, newStatus: string) => void;
    onUpdate: (nodeId: string, updates: any) => void;
    onChecklistToggle: (nodeId: string, index: number, checked: boolean) => void;
    categoryColors: Record<string, string>;
    phases: string[];
    categories: string[];
}

type SidebarTab = 'detail' | 'knowledge' | 'rag' | 'chat';

export default function IntegratedSidebar({
    selectedNode,
    knowledge,
    chatHistory,
    isSearching,
    onChatSend,
    onDragStart,
    incomingEdges,
    outgoingEdges,
    getNodeLabel,
    onNavigate,
    isEditMode,
    onStatusChange,
    onUpdate,
    onChecklistToggle,
    categoryColors,
    phases,
    categories
}: IntegratedSidebarProps) {
    const [prompt, setPrompt] = useState("");
    const [activeTab, setActiveTab] = useState<SidebarTab>('detail');
    const chatEndRef = useRef<HTMLDivElement>(null);

    // Reset tab when node changes
    useEffect(() => {
        if (selectedNode) setActiveTab('detail');
    }, [selectedNode?.id]);

    // Auto-scroll chat
    useEffect(() => {
        if (activeTab === 'chat') {
            chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }
    }, [chatHistory, activeTab]);

    if (!selectedNode) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-[var(--muted)] text-center bg-white/50">
                <MessageSquare className="w-12 h-12 mb-4 opacity-20" />
                <p className="text-sm">ノードを選択すると詳細が表示されます</p>
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

    const categoryColor = categoryColors[selectedNode.category] || '#6b7280';

    const STATUS_CONFIG: Record<string, string> = {
        '未着手': 'bg-slate-100 text-slate-500',
        '検討中': 'bg-amber-100 text-amber-700',
        '決定済み': 'bg-green-100 text-green-700',
    };
    const statusClass = STATUS_CONFIG[selectedNode.status] || STATUS_CONFIG['未着手'];

    const tabs: Array<{ id: SidebarTab; icon: any; label: string; badge?: number }> = [
        { id: 'detail', icon: FileText, label: '詳細' },
        { id: 'knowledge', icon: BookOpen, label: '知識' },
        { id: 'rag', icon: Database, label: 'RAG', badge: knowledge.length || undefined },
        { id: 'chat', icon: MessageSquare, label: 'Chat', badge: chatHistory.length || undefined },
    ];

    return (
        <div className="flex-1 flex flex-col h-full bg-white overflow-hidden shadow-lg border-l border-[var(--border)]">
            {/* Common Header */}
            <div className="p-3 border-b border-[var(--border)] bg-gradient-to-r"
                style={{ background: `linear-gradient(135deg, ${categoryColor}12, transparent)` }}
            >
                <div className="flex items-center gap-2 min-w-0">
                    <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: categoryColor }} />
                    <span className="font-semibold text-sm truncate flex-1 text-slate-800">{selectedNode.label}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 font-medium ${statusClass}`}>
                        {selectedNode.status}
                    </span>
                </div>
                <div className="flex items-center gap-1.5 mt-1 text-[10px] text-slate-400">
                    <span>{selectedNode.phase}</span>
                    <span>·</span>
                    <span>{selectedNode.category}</span>
                </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex border-b border-[var(--border)] bg-slate-50/50">
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[11px] font-medium transition-colors relative ${activeTab === tab.id
                            ? 'text-violet-600'
                            : 'text-slate-400 hover:text-slate-600'
                            }`}
                    >
                        <tab.icon className="w-3.5 h-3.5" />
                        {tab.label}
                        {tab.badge && (
                            <span className="inline-flex items-center justify-center w-4 h-4 text-[9px] bg-violet-100 text-violet-600 rounded-full">
                                {tab.badge}
                            </span>
                        )}
                        {activeTab === tab.id && (
                            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-violet-500" />
                        )}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <div className="flex-1 flex flex-col min-h-0 relative">
                {activeTab === 'detail' && (
                    <div className="flex-1 overflow-y-auto">
                        <NodeDetailPanel
                            node={selectedNode}
                            incomingEdges={incomingEdges}
                            outgoingEdges={outgoingEdges}
                            getNodeLabel={getNodeLabel}
                            categoryColor={categoryColor}
                            onClose={() => { }}
                            onNavigate={onNavigate}
                            isEditMode={isEditMode}
                            onStatusChange={onStatusChange}
                            phases={phases}
                            categories={categories}
                            onUpdate={onUpdate}
                            onChecklistToggle={onChecklistToggle}
                        />
                    </div>
                )}

                {activeTab === 'knowledge' && (
                    <div className="flex-1 overflow-y-auto p-3">
                        <KnowledgePanel
                            nodeId={selectedNode.id}
                            categoryColor={categoryColor}
                        />
                    </div>
                )}

                {activeTab === 'rag' && (
                    <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
                        {isSearching && (
                            <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                RAG検索中...
                            </div>
                        )}
                        {!isSearching && knowledge.length === 0 && (
                            <div className="text-center py-12 text-slate-400">
                                <Database className="w-8 h-8 mx-auto mb-2 opacity-20" />
                                <p className="text-xs">関連ナレッジは見つかりませんでした</p>
                            </div>
                        )}
                        {knowledge.map((item, i) => (
                            <div
                                key={i}
                                className="border border-slate-200 rounded-lg p-3 text-xs bg-white hover:border-violet-300 hover:shadow-sm transition-all cursor-grab active:cursor-grabbing group"
                                draggable
                                onDragStart={(e) => onDragStart(e, item)}
                            >
                                <div className="flex items-center justify-between gap-2 mb-1.5">
                                    <span className="font-semibold text-slate-700 truncate">{item.source}</span>
                                    <span className="text-[9px] text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded-full flex-shrink-0">
                                        {Math.round(item.relevance * 100)}%
                                    </span>
                                </div>
                                <p className="text-slate-500 line-clamp-3 leading-relaxed">
                                    {item.content}
                                </p>
                            </div>
                        ))}
                    </div>
                )}

                {activeTab === 'chat' && (
                    <div className="flex-1 flex flex-col min-h-0 bg-slate-50/30">
                        <div className="flex-1 overflow-y-auto p-3 space-y-3">
                            {chatHistory.length === 0 && (
                                <div className="text-center py-12 text-slate-400">
                                    <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-20" />
                                    <p className="text-xs">このノードについてAIに質問できます</p>
                                </div>
                            )}
                            {chatHistory.map((msg, i) => (
                                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                    <div className={`max-w-[90%] rounded-xl px-3 py-2 text-xs leading-relaxed shadow-sm ${msg.role === 'user'
                                        ? 'bg-violet-600 text-white'
                                        : 'bg-white border border-slate-200 text-slate-700 markdown-content'
                                        }`}>
                                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                                    </div>
                                </div>
                            ))}
                            <div ref={chatEndRef} />
                        </div>

                        <div className="p-3 bg-white border-t border-slate-100 flex gap-2">
                            <textarea
                                value={prompt}
                                onChange={(e) => setPrompt(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="質問を入力..."
                                rows={2}
                                className="flex-1 text-xs bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-violet-500 focus:bg-white transition-all"
                            />
                            <button
                                onClick={handleSend}
                                disabled={!prompt.trim()}
                                className="p-2.5 rounded-xl bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all self-end shadow-sm"
                            >
                                <Send className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
