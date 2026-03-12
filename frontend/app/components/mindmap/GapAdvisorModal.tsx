import React, { useState, useEffect } from 'react';
import { X, Activity, Save, Loader2, Sparkles, AlertTriangle, GitCommit, Check, History, Clock, ChevronRight } from 'lucide-react';
import { authFetch } from '@/lib/api';

export interface Suggestion {
    type: 'add_node' | 'add_edge' | 'modify_node';
    target: string;
    description: string;
    parent_id?: string; // Task-2
    source_id?: string; // Task-2
    target_id?: string; // Task-2
}

export interface StructuralIssue {
    id: string;
    label: string;
    phase: string;
}

export interface ProjectContext {
    technical_conditions: string;
    legal_requirements: string;
}

interface GapHistoryItem {
    id: string;
    timestamp: string;
    coverage_score: number;
    summary: string;
    suggestions: Suggestion[];
    focus_areas?: string[];
}

interface GapAdvisorModalProps {
    isOpen: boolean;
    onClose: () => void;
    projectId: string;
    initialContext: ProjectContext;
    onApplySuggestions?: () => void; // Called after suggestions applied to refresh project map
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export default function GapAdvisorModal({ isOpen, onClose, projectId, initialContext, onApplySuggestions }: GapAdvisorModalProps) {
    const [context, setContext] = useState<ProjectContext>(initialContext);
    const [isSavingContext, setIsSavingContext] = useState(false);
    
    const [activeTab, setActiveTab] = useState<'current' | 'history'>('current');
    const [history, setHistory] = useState<GapHistoryItem[]>([]);
    const [isLoadingHistory, setIsLoadingHistory] = useState(false);
    
    const [isChecking, setIsChecking] = useState(false);
    const [results, setResults] = useState<{
        issues: { orphans: StructuralIssue[], dead_ends: StructuralIssue[], roots: StructuralIssue[] };
        suggestions: Suggestion[];
        coverage_score: number;
        summary: string;
    } | null>(null);
    
    const [isApplying, setIsApplying] = useState(false);
    
    useEffect(() => {
        if (isOpen) {
            setContext(initialContext);
            setResults(null);
            setActiveTab('current');
            fetchHistory();
        }
    }, [isOpen, initialContext]);

    const fetchHistory = async () => {
        try {
            setIsLoadingHistory(true);
            const res = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/gap-history`);
            if (res.ok) {
                const data = await res.json();
                setHistory(data || []);
            }
        } catch (err) {
            console.error("Failed to fetch history", err);
        } finally {
            setIsLoadingHistory(false);
        }
    };

    if (!isOpen) return null;

    const handleSaveContext = async () => {
        try {
            setIsSavingContext(true);
            const res = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/context`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(context)
            });
            if (!res.ok) throw new Error('保存失敗');
        } catch (err) {
            console.error('Context save error', err);
            alert('前提条件の保存に失敗しました');
        } finally {
            setIsSavingContext(false);
        }
    };

    const handleRunGapCheck = async () => {
        try {
            setIsChecking(true);
            const res = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/ai/gap-check`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_context_override: `技術条件: ${context.technical_conditions}\n法規: ${context.legal_requirements}`
                })
            });
            if (res.status === 504) {
                alert("AI処理がタイムアウトしました。マップの規模を縮小するか、再度実行してください。");
                return;
            }
            if (!res.ok) throw new Error('Gap Checkエラー');
            const data = await res.json();
            setResults(data);
            fetchHistory(); // Refresh history after new check
        } catch (err) {
            console.error(err);
            alert('Gap Checkの実行に失敗しました');
        } finally {
            setIsChecking(false);
        }
    };

    const handleApplySuggestions = async (suggestionsToApply?: Suggestion[]) => {
        const payload = suggestionsToApply || results?.suggestions;
        if (!payload || !payload.length) return;
        
        try {
            setIsApplying(true);
            const res = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/gap-suggestions/apply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ suggestions: payload })
            });
            if (!res.ok) throw new Error('Apply error');
            if (onApplySuggestions) onApplySuggestions();
            onClose();
        } catch (err) {
            console.error(err);
            alert('提案の適用に失敗しました');
        } finally {
            setIsApplying(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
                    <div className="flex items-center gap-6">
                        <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                            <Activity className="w-5 h-5 text-fuchsia-500" />
                            Gap Advisor
                        </h2>
                        <div className="flex items-center bg-gray-200/50 p-1 rounded-lg">
                            <button 
                                onClick={() => setActiveTab('current')}
                                className={`px-4 py-1 text-xs font-bold rounded-md transition-all ${activeTab === 'current' ? 'bg-white shadow-sm text-fuchsia-600' : 'text-gray-500 hover:text-gray-700'}`}
                            >
                                現在の診断
                            </button>
                            <button 
                                onClick={() => setActiveTab('history')}
                                className={`px-4 py-1 text-xs font-bold rounded-md transition-all ${activeTab === 'history' ? 'bg-white shadow-sm text-fuchsia-600' : 'text-gray-500 hover:text-gray-700'}`}
                            >
                                <div className="flex items-center gap-1.5">
                                    <History className="w-3 h-3" />
                                    診断履歴
                                </div>
                            </button>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                
                <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
                    {activeTab === 'current' ? (
                        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
                            {/* Left side: Context configuration */}
                            <div className="md:w-1/3 flex flex-col gap-4 border-r border-slate-100 p-6 overflow-y-auto">
                                <h3 className="text-sm font-semibold text-slate-700 flex items-center justify-between">
                                    前提条件 (Context)
                                    <button 
                                        onClick={handleSaveContext}
                                        disabled={isSavingContext}
                                        className="text-xs text-blue-600 hover:text-blue-700 bg-blue-50 px-2 py-1 rounded flex items-center gap-1"
                                    >
                                        {isSavingContext ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                                        保存
                                    </button>
                                </h3>
                                
                                <div className="space-y-3">
                                    <div>
                                        <label className="block text-xs font-medium text-slate-500 mb-1">技術要件 (Technical)</label>
                                        <textarea 
                                            value={context.technical_conditions}
                                            onChange={e => setContext({ ...context, technical_conditions: e.target.value })}
                                            className="w-full h-24 text-xs p-3 border border-slate-200 rounded-md focus:ring-2 focus:ring-fuchsia-100 focus:border-fuchsia-300 resize-none leading-relaxed"
                                            placeholder="例: S造2階建て、1階RC造..."
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-slate-500 mb-1">法規条件 (Legal)</label>
                                        <textarea 
                                            value={context.legal_requirements}
                                            onChange={e => setContext({ ...context, legal_requirements: e.target.value })}
                                            className="w-full h-24 text-xs p-3 border border-slate-200 rounded-md focus:ring-2 focus:ring-fuchsia-100 focus:border-fuchsia-300 resize-none leading-relaxed"
                                            placeholder="例: 防火地域指定あり、日影規制なし..."
                                        />
                                    </div>
                                </div>

                                <button
                                    onClick={handleRunGapCheck}
                                    disabled={isChecking}
                                    className="w-full mt-4 flex items-center justify-center gap-2 bg-gradient-to-r from-fuchsia-500 to-violet-500 text-white font-bold py-3 rounded-lg shadow-md hover:shadow-lg transition-all disabled:opacity-50"
                                >
                                    {isChecking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                                    AI診断を実行
                                </button>
                            </div>

                            {/* Right side: Results */}
                            <div className="md:w-2/3 flex flex-col p-6 overflow-y-auto">
                                {!results && !isChecking && (
                                    <div className="flex-1 flex flex-col items-center justify-center text-slate-400 py-12">
                                        <Activity className="w-16 h-16 mb-4 opacity-10" />
                                        <p className="text-sm font-medium">条件を入力し、AIによるGap診断を実行してください。</p>
                                    </div>
                                )}
                                
                                {isChecking && (
                                    <div className="flex-1 flex flex-col items-center justify-center text-fuchsia-500 space-y-6 py-12">
                                        <div className="relative">
                                            <div className="absolute inset-0 border-8 border-fuchsia-100 rounded-full animate-ping opacity-75"></div>
                                            <Loader2 className="w-16 h-16 animate-spin relative z-10" />
                                        </div>
                                        <div className="text-center">
                                            <p className="text-lg font-bold animate-pulse mb-1">分析中...</p>
                                            <p className="text-xs text-slate-400">マインドマップの全構造を文脈に照らして評価しています</p>
                                        </div>
                                    </div>
                                )}

                                {results && (
                                    <div className="space-y-6">
                                        {/* Task-1: Score and Summary */}
                                        <section className="bg-gradient-to-br from-slate-50 to-white border border-slate-200 rounded-xl p-5 shadow-sm">
                                            <div className="flex items-start gap-6">
                                                <div className="flex-shrink-0 text-center">
                                                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Coverage</div>
                                                    <div className="relative inline-flex items-center justify-center">
                                                        <svg className="w-20 h-20">
                                                            <circle className="text-slate-200" strokeWidth="6" stroke="currentColor" fill="transparent" r="34" cx="40" cy="40" />
                                                            <circle className="text-fuchsia-500 transition-all duration-1000 ease-out" strokeWidth="6" strokeDasharray={2 * Math.PI * 34} strokeDashoffset={2 * Math.PI * 34 * (1 - results.coverage_score / 100)} strokeLinecap="round" stroke="currentColor" fill="transparent" r="34" cx="40" cy="40" />
                                                        </svg>
                                                        <span className="absolute text-xl font-black text-fuchsia-600">{results.coverage_score}%</span>
                                                    </div>
                                                </div>
                                                <div className="flex-1 pt-1">
                                                    <h3 className="text-sm font-bold text-slate-800 mb-2">診断サマリー</h3>
                                                    <p className="text-sm text-slate-600 leading-relaxed italic border-l-2 border-fuchsia-200 pl-4">
                                                        "{results.summary}"
                                                    </p>
                                                </div>
                                            </div>
                                        </section>

                                        {/* Structural Issues */}
                                        <section>
                                            <h4 className="text-xs font-bold text-rose-500 flex items-center gap-1.5 mb-2 uppercase tracking-wide">
                                                <AlertTriangle className="w-3.5 h-3.5" /> 構造上の課題
                                            </h4>
                                            <div className="bg-rose-50/50 border border-rose-100 rounded-lg p-3 text-xs space-y-3">
                                                {results.issues.orphans.length > 0 && (
                                                    <div>
                                                        <span className="font-bold text-rose-700">孤立ノード (Orphans):</span>
                                                        <ul className="mt-1 ml-4 list-disc text-rose-600">
                                                            {results.issues.orphans.map(i => <li key={i.id}>{i.label} <span className="text-[10px] opacity-70">({i.phase})</span></li>)}
                                                        </ul>
                                                    </div>
                                                )}
                                                {results.issues.dead_ends.length > 0 && (
                                                    <div>
                                                        <span className="font-bold text-orange-700">行き止まり (Dead-ends):</span>
                                                        <ul className="mt-1 ml-4 list-disc text-orange-600">
                                                            {results.issues.dead_ends.map(i => <li key={i.id}>{i.label} <span className="text-[10px] opacity-70">({i.phase})</span></li>)}
                                                        </ul>
                                                    </div>
                                                )}
                                                {results.issues.orphans.length === 0 && results.issues.dead_ends.length === 0 && (
                                                    <div className="text-emerald-600 font-bold flex items-center gap-1.5 py-1">
                                                        <Check className="w-4 h-4" /> 構造上の重大なエラーは見つかりませんでした。
                                                    </div>
                                                )}
                                            </div>
                                        </section>

                                        {/* AI Suggestions */}
                                        <section>
                                            <h4 className="text-xs font-bold text-indigo-500 flex items-center gap-1.5 mb-2 uppercase tracking-wide">
                                                <Sparkles className="w-3.5 h-3.5" /> 推奨アクション ({results.suggestions.length})
                                            </h4>
                                            <div className="space-y-2.5">
                                                {results.suggestions.map((s, idx) => (
                                                    <div key={idx} className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm hover:border-indigo-300 transition-all group">
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm ${
                                                                s.type === 'add_node' ? 'bg-green-100 text-green-700' :
                                                                s.type === 'add_edge' ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'
                                                            }`}>
                                                                {s.type === 'add_node' ? 'ノード追加' : s.type === 'add_edge' ? '依存関係追加' : 'ノード変更'}
                                                            </span>
                                                            <span className="font-bold text-slate-800">{s.target}</span>
                                                        </div>
                                                        <p className="text-sm text-slate-600 leading-normal pl-1">{s.description}</p>
                                                        {s.parent_id && (
                                                            <div className="mt-2 text-[10px] text-slate-400 bg-slate-50 px-2 py-1 rounded inline-block">
                                                                🔗 接続先ID: {s.parent_id}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </section>

                                        <div className="pt-6 mt-6 border-t border-slate-100 flex justify-end sticky bottom-0 bg-white pb-2">
                                            <button
                                                onClick={() => handleApplySuggestions()}
                                                disabled={isApplying || results.suggestions.length === 0}
                                                className="flex items-center gap-2 bg-indigo-600 text-white px-6 py-2.5 rounded-xl font-bold hover:bg-indigo-700 shadow-lg shadow-indigo-100 transition-all disabled:opacity-50"
                                            >
                                                {isApplying ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCommit className="w-4 h-4" />}
                                                現在の提案をマップに適用する
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    ) : (
                        /* Task-3: History Tab */
                        <div className="flex-1 flex flex-col p-6 overflow-y-auto bg-slate-50/30">
                            {isLoadingHistory ? (
                                <div className="flex-1 flex items-center justify-center">
                                    <Loader2 className="w-8 h-8 animate-spin text-slate-300" />
                                </div>
                            ) : history.length === 0 ? (
                                <div className="flex-1 flex flex-col items-center justify-center text-slate-400 py-12">
                                    <History className="w-16 h-16 mb-4 opacity-10" />
                                    <p className="text-sm font-medium">診断履歴はまだありません。</p>
                                </div>
                            ) : (
                                <div className="space-y-4 max-w-4xl mx-auto w-full">
                                    {history.map((item, idx) => (
                                        <div key={item.id || idx} className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm hover:border-fuchsia-200 transition-all group">
                                            <div className="px-5 py-4 flex items-center justify-between border-b border-slate-50">
                                                <div className="flex items-center gap-4">
                                                    <div className="bg-slate-100 p-2 rounded-lg">
                                                        <Clock className="w-4 h-4 text-slate-500" />
                                                    </div>
                                                    <div>
                                                        <p className="text-xs font-bold text-slate-800">
                                                            {new Date(item.timestamp).toLocaleString('ja-JP')}
                                                        </p>
                                                        <p className="text-[10px] text-slate-400">
                                                            提案数: {item.suggestions?.length || 0}件
                                                        </p>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-6">
                                                    <div className="text-right">
                                                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Score</div>
                                                        <div className="text-lg font-black text-fuchsia-600">{item.coverage_score}%</div>
                                                    </div>
                                                    <button 
                                                        onClick={() => {
                                                            setResults({
                                                                issues: { orphans: [], dead_ends: [], roots: [] },
                                                                suggestions: item.suggestions || [],
                                                                coverage_score: item.coverage_score,
                                                                summary: item.summary
                                                            });
                                                            setActiveTab('current');
                                                        }}
                                                        className="p-2 hover:bg-fuchsia-50 rounded-lg text-fuchsia-400 group-hover:text-fuchsia-600 transition-all"
                                                    >
                                                        <ChevronRight className="w-5 h-5" />
                                                    </button>
                                                </div>
                                            </div>
                                            <div className="px-5 py-3 bg-slate-50/50">
                                                <p className="text-[11px] text-slate-500 leading-relaxed line-clamp-2">
                                                    {item.summary}
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
