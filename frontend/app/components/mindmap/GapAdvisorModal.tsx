import React, { useState, useEffect } from 'react';
import { X, Activity, Save, Loader2, Sparkles, AlertTriangle, GitCommit, Check } from 'lucide-react';
import { authFetch } from '@/lib/api';

export interface Suggestion {
    type: 'add_node' | 'add_edge' | 'modify_node';
    target: string;
    description: string;
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
    
    const [isChecking, setIsChecking] = useState(false);
    const [results, setResults] = useState<{
        issues: { orphans: StructuralIssue[], dead_ends: StructuralIssue[], roots: StructuralIssue[] };
        suggestions: Suggestion[];
    } | null>(null);
    
    const [isApplying, setIsApplying] = useState(false);
    
    useEffect(() => {
        if (isOpen) {
            setContext(initialContext);
            setResults(null);
        }
    }, [isOpen, initialContext]);

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
            if (!res.ok) throw new Error('Gap Checkエラー');
            const data = await res.json();
            setResults(data);
        } catch (err) {
            console.error(err);
            alert('Gap Checkの実行に失敗しました');
        } finally {
            setIsChecking(false);
        }
    };

    const handleApplySuggestions = async () => {
        if (!results || !results.suggestions.length) return;
        try {
            setIsApplying(true);
            const res = await authFetch(`${API_BASE}/api/mindmap/projects/${projectId}/gap-suggestions/apply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ suggestions: results.suggestions })
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
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
                    <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                        <Activity className="w-5 h-5 text-fuchsia-500" />
                        Gap Advisor (AI チェック)
                    </h2>
                    <button onClick={onClose} className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                
                <div className="flex-1 overflow-y-auto p-6 flex flex-col md:flex-row gap-6">
                    {/* Left side: Context configuration */}
                    <div className="md:w-1/3 flex flex-col gap-4 border-r border-slate-100 pr-6">
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
                                    className="w-full h-24 text-xs p-2 border border-slate-200 rounded-md focus:ring-2 focus:ring-fuchsia-100 focus:border-fuchsia-300 resize-none"
                                    placeholder="例: S造2階建て、1階RC造..."
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-500 mb-1">法規条件 (Legal)</label>
                                <textarea 
                                    value={context.legal_requirements}
                                    onChange={e => setContext({ ...context, legal_requirements: e.target.value })}
                                    className="w-full h-24 text-xs p-2 border border-slate-200 rounded-md focus:ring-2 focus:ring-fuchsia-100 focus:border-fuchsia-300 resize-none"
                                    placeholder="例: 防火地域指定あり、日影規制なし..."
                                />
                            </div>
                        </div>

                        <button
                            onClick={handleRunGapCheck}
                            disabled={isChecking}
                            className="w-full mt-4 flex items-center justify-center gap-2 bg-gradient-to-r from-fuchsia-500 to-violet-500 text-white font-medium py-2.5 rounded-lg shadow-md hover:shadow-lg transition-all disabled:opacity-50"
                        >
                            {isChecking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                            AIによる構造とGap診断
                        </button>
                    </div>

                    {/* Right side: Results */}
                    <div className="md:w-2/3 flex flex-col">
                        <h3 className="text-sm font-semibold text-slate-700 mb-4">分析結果 (Insights)</h3>
                        
                        {!results && !isChecking && (
                            <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                                <Activity className="w-12 h-12 mb-3 opacity-20" />
                                <p className="text-sm">条件を入力し、Gap診断を実行してください。</p>
                            </div>
                        )}
                        
                        {isChecking && (
                            <div className="flex-1 flex flex-col items-center justify-center text-fuchsia-500 space-y-4">
                                <div className="relative">
                                    <div className="absolute inset-0 border-4 border-fuchsia-200 rounded-full animate-ping opacity-75"></div>
                                    <Loader2 className="w-12 h-12 animate-spin relative z-10" />
                                </div>
                                <p className="text-sm font-medium animate-pulse">プロジェクト構造と要件を網羅的に分析中...</p>
                            </div>
                        )}

                        {results && (
                            <div className="space-y-6">
                                {/* Structural Issues */}
                                <div>
                                    <h4 className="text-xs font-bold text-rose-500 flex items-center gap-1.5 mb-2 uppercase tracking-wide">
                                        <AlertTriangle className="w-3.5 h-3.5" /> 構造上の懸念点
                                    </h4>
                                    <div className="bg-rose-50/50 border border-rose-100 rounded-lg p-3 text-xs space-y-3">
                                        {results.issues.orphans.length > 0 && (
                                            <div>
                                                <span className="font-semibold text-rose-700">孤立ノード (Orphans):</span>
                                                <ul className="mt-1 ml-4 list-disc text-rose-600">
                                                    {results.issues.orphans.map(i => <li key={i.id}>{i.label} <span className="text-[10px] opacity-70">({i.phase})</span></li>)}
                                                </ul>
                                            </div>
                                        )}
                                        {results.issues.dead_ends.length > 0 && (
                                            <div>
                                                <span className="font-semibold text-orange-700">行き止まり (Dead-ends):</span>
                                                <ul className="mt-1 ml-4 list-disc text-orange-600">
                                                    {results.issues.dead_ends.map(i => <li key={i.id}>{i.label} <span className="text-[10px] opacity-70">({i.phase})</span></li>)}
                                                </ul>
                                            </div>
                                        )}
                                        {results.issues.orphans.length === 0 && results.issues.dead_ends.length === 0 && (
                                            <div className="text-emerald-600 flex items-center gap-1">
                                                <Check className="w-3.5 h-3.5" /> 構造上の明らかなエラーは見つかりませんでした。
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* AI Suggestions */}
                                <div>
                                    <h4 className="text-xs font-bold text-indigo-500 flex items-center gap-1.5 mb-2 uppercase tracking-wide">
                                        <Sparkles className="w-3.5 h-3.5" /> 推奨アクション (Gap Suggestions)
                                    </h4>
                                    <div className="space-y-2">
                                        {results.suggestions.map((s, idx) => (
                                            <div key={idx} className="bg-white border border-slate-200 rounded-lg p-3 shadow-sm hover:border-indigo-300 transition-colors">
                                                <div className="flex items-center gap-2 mb-1.5">
                                                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-sm ${
                                                        s.type === 'add_node' ? 'bg-green-100 text-green-700' :
                                                        s.type === 'add_edge' ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'
                                                    }`}>
                                                        {s.type === 'add_node' ? 'ノード追加' : s.type === 'add_edge' ? '依存関係追加' : 'ノード変更'}
                                                    </span>
                                                    <span className="font-semibold text-sm text-slate-800">{s.target}</span>
                                                </div>
                                                <p className="text-xs text-slate-600 pl-1">{s.description}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div className="pt-4 border-t border-slate-100 flex justify-end">
                                    <button
                                        onClick={handleApplySuggestions}
                                        disabled={isApplying || results.suggestions.length === 0}
                                        className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50"
                                    >
                                        {isApplying ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCommit className="w-4 h-4" />}
                                        マップへ適用する
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
