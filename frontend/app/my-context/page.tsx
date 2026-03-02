'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { ChevronLeft, ChevronDown, ChevronRight, Plus, Trash2, Power } from 'lucide-react';
import { authFetch } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

type ContextType = 'judgement' | 'lesson' | 'insight';

interface PersonalContext {
    id: number;
    type: ContextType;
    content: string;
    trigger_keywords: string[];
    project_tag: string | null;
    source_question: string | null;
    merge_history: any[];
    updated_at: string;
    is_active: boolean;
}

export default function MyContextPage() {
    const [contexts, setContexts] = useState<PersonalContext[]>([]);
    const [activeTab, setActiveTab] = useState<ContextType>('judgement');
    const [isLoading, setIsLoading] = useState(true);

    // Form state
    const [newContent, setNewContent] = useState('');
    const [newType, setNewType] = useState<ContextType>('judgement');
    const [newKeywords, setNewKeywords] = useState('');

    // UI state
    const [expandedHistory, setExpandedHistory] = useState<Record<number, boolean>>({});
    const [expandedSource, setExpandedSource] = useState<Record<number, boolean>>({});

    const fetchContexts = async () => {
        setIsLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/personal-contexts`);
            if (res.ok) {
                const data = await res.json();
                setContexts(data);
            }
        } catch (error) {
            console.error(error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchContexts();
    }, []);

    const toggleActive = async (id: number, currentStatus: boolean) => {
        try {
            const res = await authFetch(`${API_BASE}/api/personal-contexts/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: !currentStatus })
            });
            if (res.ok) {
                fetchContexts();
            }
        } catch (error) {
            console.error(error);
        }
    };

    const handleDelete = async (id: number) => {
        if (!confirm('本当に削除しますか？')) return;
        try {
            const res = await authFetch(`${API_BASE}/api/personal-contexts/${id}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                fetchContexts();
            }
        } catch (error) {
            console.error(error);
        }
    };

    const handleAdd = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newContent.trim()) return;

        const keywords = newKeywords.split(',').map(k => k.trim()).filter(k => k);
        try {
            const res = await authFetch(`${API_BASE}/api/personal-contexts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type: newType,
                    content: newContent,
                    trigger_keywords: keywords,
                    project_tag: null
                })
            });
            if (res.ok) {
                setNewContent('');
                setNewKeywords('');
                fetchContexts();
            }
        } catch (error) {
            console.error(error);
            alert('追加に失敗しました');
        }
    };

    const filteredContexts = contexts.filter(c => c.type === activeTab);

    return (
        <div className="min-h-screen bg-slate-50 text-slate-900">
            <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
                <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link href="/" className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                            <ChevronLeft className="w-5 h-5" />
                        </Link>
                        <h1 className="text-xl font-bold text-slate-800">My Context (Mem0)</h1>
                    </div>
                </div>
            </header>

            <main className="max-w-5xl mx-auto px-4 py-8 grid grid-cols-1 md:grid-cols-3 gap-8">
                {/* Left col: Context list */}
                <div className="md:col-span-2 space-y-6">
                    {/* Tabs */}
                    <div className="flex border-b border-slate-200">
                        {(['judgement', 'lesson', 'insight'] as ContextType[]).map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === tab
                                        ? 'border-violet-600 text-violet-700'
                                        : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                                    }`}
                            >
                                {tab.toUpperCase()}
                            </button>
                        ))}
                    </div>

                    {/* List */}
                    {isLoading ? (
                        <div className="text-center py-12 text-slate-400">Loading...</div>
                    ) : filteredContexts.length === 0 ? (
                        <div className="text-center py-12 text-slate-400 bg-white rounded-xl border border-slate-200">
                            エントリがありません
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {filteredContexts.map(ctx => (
                                <div key={ctx.id} className={`bg-white rounded-xl border ${ctx.is_active ? 'border-slate-200 shadow-sm' : 'border-slate-200 bg-slate-50 opacity-60'} p-5 transition-all`}>
                                    <div className="flex justify-between items-start gap-4 mb-3">
                                        <p className={`text-base font-medium ${!ctx.is_active && 'line-through text-slate-500'}`}>
                                            {ctx.content}
                                        </p>
                                        <div className="flex items-center gap-2 shrink-0">
                                            <button
                                                onClick={() => toggleActive(ctx.id, ctx.is_active)}
                                                className={`p-1.5 rounded-lg border text-xs font-bold transition-colors ${ctx.is_active ? 'bg-green-50 text-green-600 border-green-200 hover:bg-green-100' : 'bg-slate-100 text-slate-400 border-slate-200 hover:bg-slate-200'}`}
                                                title={ctx.is_active ? "無効化する" : "有効化する"}
                                            >
                                                <Power className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => handleDelete(ctx.id)}
                                                className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                                title="削除"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>

                                    <div className="flex flex-wrap gap-2 mb-4">
                                        {ctx.trigger_keywords.map((kw, i) => (
                                            <span key={i} className="px-2 py-0.5 bg-blue-50 text-blue-600 text-[10px] font-medium rounded border border-blue-100">
                                                {kw}
                                            </span>
                                        ))}
                                    </div>

                                    <div className="text-[11px] text-slate-400 flex items-center gap-4 mb-4">
                                        <span>Update: {new Date(ctx.updated_at).toLocaleString('ja-JP')}</span>
                                    </div>

                                    {/* Accordions */}
                                    <div className="space-y-2 border-t border-slate-100 pt-3">
                                        {ctx.source_question && (
                                            <div>
                                                <button
                                                    onClick={() => setExpandedSource(prev => ({ ...prev, [ctx.id]: !prev[ctx.id] }))}
                                                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 transition-colors"
                                                >
                                                    {expandedSource[ctx.id] ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                                                    元の発言 (Source Question)
                                                </button>
                                                {expandedSource[ctx.id] && (
                                                    <div className="mt-2 ml-4 p-2 bg-slate-50 text-slate-600 text-xs rounded border border-slate-100">
                                                        {ctx.source_question}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        {ctx.merge_history && ctx.merge_history.length > 0 && (
                                            <div>
                                                <button
                                                    onClick={() => setExpandedHistory(prev => ({ ...prev, [ctx.id]: !prev[ctx.id] }))}
                                                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 transition-colors"
                                                >
                                                    {expandedHistory[ctx.id] ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                                                    更新履歴 ({ctx.merge_history.length}件のマージ)
                                                </button>
                                                {expandedHistory[ctx.id] && (
                                                    <div className="mt-2 ml-4 space-y-2">
                                                        {ctx.merge_history.map((mh, i) => (
                                                            <div key={i} className="p-2 bg-yellow-50/50 text-slate-600 text-xs rounded border border-yellow-100">
                                                                <div className="font-medium text-[10px] text-yellow-700 mb-1">
                                                                    {new Date(mh.merged_at).toLocaleString('ja-JP')}
                                                                </div>
                                                                <div className="line-through opacity-70 mb-1">{mh.original}</div>
                                                                {mh.source_question && <div className="text-yellow-600/80 italic">From: {mh.source_question}</div>}
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Right col: Manual add form */}
                <div>
                    <div className="bg-white rounded-xl border border-slate-200 p-5 sticky top-24 shadow-sm">
                        <h2 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
                            <Plus className="w-4 h-4 text-violet-600" />
                            手動でナレッジを追加
                        </h2>
                        <form onSubmit={handleAdd} className="space-y-4">
                            <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1.5">種別 (Type)</label>
                                <select
                                    value={newType}
                                    onChange={e => setNewType(e.target.value as ContextType)}
                                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-violet-500 focus:outline-none"
                                >
                                    <option value="judgement">Judgement (判断基準)</option>
                                    <option value="lesson">Lesson (失敗・教訓)</option>
                                    <option value="insight">Insight (気づき)</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1.5">内容 (要約)</label>
                                <textarea
                                    value={newContent}
                                    onChange={e => setNewContent(e.target.value)}
                                    placeholder="例: ECI方式では早期にゼネコンを選定する"
                                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 h-20 resize-none focus:ring-2 focus:ring-violet-500 focus:outline-none"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1.5">トリガーキーワード</label>
                                <input
                                    type="text"
                                    value={newKeywords}
                                    onChange={e => setNewKeywords(e.target.value)}
                                    placeholder="カンマ区切り (例: ECI, 選定)"
                                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-violet-500 focus:outline-none"
                                />
                            </div>
                            <button
                                type="submit"
                                className="w-full bg-violet-600 hover:bg-violet-700 text-white font-medium text-sm py-2.5 rounded-lg transition-colors"
                            >
                                追加する
                            </button>
                        </form>
                    </div>
                </div>
            </main>
        </div>
    );
}
