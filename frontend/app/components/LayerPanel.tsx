'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
    Layers,
    Info,
    Shield,
    User,
    Zap,
    RefreshCw,
    Save,
    Trash2,
    Check,
    AlertTriangle,
    FileText,
    Sparkles,
    ChevronDown,
    ChevronRight,
    Folder,
    Loader2,
    Clock,
    Files,
    X,
    Type
} from 'lucide-react';
import {
    authFetch,
    API_BASE,
    contextSheetStream,
    listContextSheets,
    deleteContextSheet,
    getContextSheet
} from '@/lib/api';
import type { ContextSheetSummary, StreamUpdate } from '@/lib/api';

// --- Types ---
interface PersonalContext {
    id: number;
    type: string;
    content: string;
    trigger_keywords: string[];
    project_tag: string | null;
    created_at: string;
    updated_at: string;
}

interface FileNode {
    name: string;
    type: 'directory' | 'file';
    path: string;
    children?: FileNode[];
}

interface LayerPanelProps {
    activeLayerB: string | null;
    activeLayerBTitle: string | null;
    onLayerBChange: (content: string | null, title: string | null) => void;
    availableModels: Record<string, string>;
    availableRoles: Record<string, string>;
}

const ROLE_LABELS: Record<string, string> = {
    pmcm: 'PMCM',
    designer: '設計者',
    cost: 'コスト管理者',
};

// --- Helper Components ---

function MdTreeNode({
    node,
    level,
    selectedPaths,
    onToggle,
}: {
    node: FileNode;
    level: number;
    selectedPaths: Set<string>;
    onToggle: (node: FileNode, checked: boolean) => void;
}) {
    const [isOpen, setIsOpen] = useState(level < 2);

    const filteredChildren = node.children?.filter(
        (c) => c.type === 'directory' || c.name.endsWith('.md')
    );

    if (node.type === 'file') {
        if (!node.name.endsWith('.md')) return null;
        return (
            <div
                className="flex items-center gap-1.5 py-0.5 px-1 rounded hover:bg-white/5 cursor-pointer"
                style={{ paddingLeft: `${level * 16 + 4}px` }}
                onClick={() => onToggle(node, !selectedPaths.has(node.path))}
            >
                <input
                    type="checkbox"
                    checked={selectedPaths.has(node.path)}
                    onChange={(e) => { e.stopPropagation(); onToggle(node, e.target.checked); }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-3 h-3 rounded border-[var(--border)] accent-violet-500 cursor-pointer flex-shrink-0"
                />
                <FileText className="w-3 h-3 text-blue-400 flex-shrink-0" />
                <span className="text-xs text-[var(--foreground)] truncate" title={node.path}>{node.name}</span>
            </div>
        );
    }

    const hasMd = (n: FileNode): boolean =>
        n.type === 'file' ? n.name.endsWith('.md') : (n.children?.some(hasMd) ?? false);
    if (!hasMd(node)) return null;

    const allMdInFolder: string[] = [];
    const collectMd = (n: FileNode) => {
        if (n.type === 'file' && n.name.endsWith('.md')) allMdInFolder.push(n.path);
        n.children?.forEach(collectMd);
    };
    collectMd(node);
    const allChecked = allMdInFolder.length > 0 && allMdInFolder.every((p) => selectedPaths.has(p));
    const someChecked = allMdInFolder.some((p) => selectedPaths.has(p));
    const indeterminate = someChecked && !allChecked;

    return (
        <div>
            <div
                className="flex items-center gap-1.5 py-0.5 px-1 rounded hover:bg-white/5 cursor-pointer"
                style={{ paddingLeft: `${level * 16 + 4}px` }}
                onClick={() => setIsOpen((o) => !o)}
            >
                <input
                    type="checkbox"
                    checked={allChecked}
                    ref={(el) => { if (el) el.indeterminate = indeterminate; }}
                    onChange={(e) => { e.stopPropagation(); onToggle(node, e.target.checked); }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-3 h-3 rounded border-[var(--border)] accent-violet-500 cursor-pointer flex-shrink-0"
                />
                {isOpen
                    ? <ChevronDown className="w-3 h-3 text-[var(--muted)] flex-shrink-0" />
                    : <ChevronRight className="w-3 h-3 text-[var(--muted)] flex-shrink-0" />
                }
                <Folder className="w-3 h-3 text-yellow-500 fill-yellow-500 flex-shrink-0" />
                <span className="text-xs font-medium text-[var(--foreground)]">{node.name}</span>
                <span className="text-[10px] text-[var(--muted)] ml-1">({allMdInFolder.length})</span>
            </div>
            {isOpen && filteredChildren && (
                <div>
                    {filteredChildren.map((child, i) => (
                        <MdTreeNode key={i} node={child} level={level + 1} selectedPaths={selectedPaths} onToggle={onToggle} />
                    ))}
                </div>
            )}
        </div>
    );
}

// --- Main Component ---

export default function LayerPanel({
    activeLayerB,
    activeLayerBTitle,
    onLayerBChange,
    availableModels,
    availableRoles
}: LayerPanelProps) {
    const [activeTab, setActiveTab] = useState<'status' | 'layer0' | 'layerA' | 'layerB'>('status');
    const [layerBSubTab, setLayerBSubTab] = useState<'text' | 'md'>('text');

    // Common State
    const [status, setStatus] = useState<{
        layer0: { char_count: number; file_exists: boolean; updated_at?: string } | null;
        layerA: { count: number } | null;
    }>({ layer0: null, layerA: null });

    // Layer 0 State
    const [layer0Text, setLayer0Text] = useState('');
    const [layer0Loading, setLayer0Loading] = useState(false);
    const [layer0Saving, setLayer0Saving] = useState(false);

    // Layer A State
    const [personalContexts, setPersonalContexts] = useState<PersonalContext[]>([]);
    const [layerALoading, setLayerALoading] = useState(false);

    // Layer B (Manual Text) State
    const [manualLayerBTitle, setManualLayerBTitle] = useState('');
    const [manualLayerBText, setManualLayerBText] = useState('');

    // Layer B (MD Generation) State
    const [selectedModel, setSelectedModel] = useState('gemini-3-flash-preview');
    const [selectedRole, setSelectedRole] = useState('pmcm');
    const [charLimit, setCharLimit] = useState(80000);
    const [sheetTitle, setSheetTitle] = useState('');
    const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
    const [tree, setTree] = useState<FileNode | null>(null);
    const [treeLoading, setTreeLoading] = useState(false);
    const [savedSheets, setSavedSheets] = useState<ContextSheetSummary[]>([]);
    const [savedLoading, setSavedLoading] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);

    // Status Refresh
    const refreshStatus = async () => {
        try {
            const [layer0Res, layerARes] = await Promise.all([
                authFetch(`${API_BASE}/api/system/layer0`),
                authFetch(`${API_BASE}/api/personal-contexts`)
            ]);

            if (layer0Res.ok && layerARes.ok) {
                const layer0 = await layer0Res.json();
                const layerA = await layerARes.json();
                setStatus({
                    layer0,
                    layerA: { count: Array.isArray(layerA) ? layerA.length : 0 }
                });
                if (activeTab === 'layer0') setLayer0Text(layer0.content);
                if (activeTab === 'layerA') setPersonalContexts(layerA);
            }
        } catch (err) {
            console.error('Failed to refresh status', err);
        }
    };

    useEffect(() => {
        refreshStatus();
    }, [activeTab]);

    // Layer 0 Actions
    const saveLayer0 = async () => {
        setLayer0Saving(true);
        try {
            const res = await authFetch(`${API_BASE}/api/system/layer0/text`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: layer0Text })
            });
            if (res.ok) {
                refreshStatus();
                alert('Layer 0 を保存しました');
            }
        } catch (err) {
            console.error(err);
        } finally {
            setLayer0Saving(false);
        }
    };

    const reloadLayer0 = async () => {
        setLayer0Loading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/system/layer0/reload`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                refreshStatus();
            }
        } catch (err) {
            console.error(err);
        } finally {
            setLayer0Loading(false);
        }
    };

    // Layer A Actions
    const deletePersonalContext = async (id: number) => {
        if (!confirm('このコンテキストを削除しますか？')) return;
        try {
            const res = await authFetch(`${API_BASE}/api/personal-contexts/${id}`, { method: 'DELETE' });
            if (res.ok) {
                refreshStatus();
            }
        } catch (err) {
            console.error(err);
        }
    };

    // Layer B Actions
    const applyManualLayerB = () => {
        const text = manualLayerBText.trim();
        const title = manualLayerBTitle.trim() || '手動入力コンテキスト';
        if (!text) {
            onLayerBChange(null, null);
        } else {
            onLayerBChange(text, title);
        }
    };

    const clearLayerB = () => {
        onLayerBChange(null, null);
        setManualLayerBText('');
        setManualLayerBTitle('');
        setSelectedPaths(new Set());
    };

    // Layer B (MD) Actions
    const fetchTree = async () => {
        setTreeLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/files/tree`);
            if (res.ok) setTree(await res.json());
        } finally {
            setTreeLoading(false);
        }
    };

    const fetchSavedSheets = async () => {
        setSavedLoading(true);
        try {
            const sheets = await listContextSheets();
            setSavedSheets(sheets);
        } finally {
            setSavedLoading(false);
        }
    };

    useEffect(() => {
        if (activeTab === 'layerB' && layerBSubTab === 'md') {
            if (!tree) fetchTree();
            fetchSavedSheets();
        }
    }, [activeTab, layerBSubTab]);

    const handleToggle = (node: FileNode, checked: boolean) => {
        setSelectedPaths((prev) => {
            const next = new Set(prev);
            const toggle = (n: FileNode) => {
                if (n.type === 'file' && n.name.endsWith('.md')) {
                    checked ? next.add(n.path) : next.delete(n.path);
                }
                n.children?.forEach(toggle);
            };
            toggle(node);
            return next;
        });
    };

    const handleGenerateLayerB = async () => {
        if (selectedPaths.size === 0 || isGenerating) return;
        setIsGenerating(true);
        try {
            let accumulated = '';
            for await (const update of contextSheetStream({
                file_paths: Array.from(selectedPaths),
                role: selectedRole,
                model: selectedModel,
                char_limit: charLimit,
                title: sheetTitle.trim() || undefined,
            })) {
                if (update.type === 'answer') {
                    accumulated += update.data;
                } else if (update.type === 'saved') {
                    fetchSavedSheets();
                    onLayerBChange(accumulated, sheetTitle.trim() || `シート #${update.id}`);
                }
            }
        } catch (err) {
            console.error(err);
        } finally {
            setIsGenerating(false);
        }
    };

    const handleApplySavedSheet = async (sheet: ContextSheetSummary) => {
        try {
            const detail = await getContextSheet(sheet.id);
            if (detail.content) {
                onLayerBChange(detail.content, sheet.title || `シート #${sheet.id}`);
            }
        } catch (err) {
            console.error(err);
        }
    };

    const handleDeleteSavedSheet = async (id: number) => {
        if (!confirm('このシートを削除しますか？')) return;
        try {
            await deleteContextSheet(id);
            fetchSavedSheets();
        } catch (err) {
            console.error(err);
        }
    };


    return (
        <div className="flex flex-col h-full bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden shadow-sm">
            {/* Tabs Header */}
            <div className="flex border-b border-[var(--border)] bg-[var(--background)]/50">
                <button
                    onClick={() => setActiveTab('status')}
                    className={`flex-1 py-2.5 text-xs font-medium flex items-center justify-center gap-1.5 transition-colors ${activeTab === 'status' ? 'text-primary-400 border-b-2 border-primary-500 bg-primary-500/5' : 'text-[var(--muted)] hover:text-[var(--foreground)]'}`}
                >
                    <Zap className="w-3.5 h-3.5" />
                    Status
                </button>
                <button
                    onClick={() => setActiveTab('layer0')}
                    className={`flex-1 py-2.5 text-xs font-medium flex items-center justify-center gap-1.5 transition-colors ${activeTab === 'layer0' ? 'text-amber-400 border-b-2 border-amber-500 bg-amber-500/5' : 'text-[var(--muted)] hover:text-[var(--foreground)]'}`}
                >
                    <Shield className="w-3.5 h-3.5" />
                    Layer 0
                </button>
                <button
                    onClick={() => setActiveTab('layerA')}
                    className={`flex-1 py-2.5 text-xs font-medium flex items-center justify-center gap-1.5 transition-colors ${activeTab === 'layerA' ? 'text-emerald-400 border-b-2 border-emerald-500 bg-emerald-500/5' : 'text-[var(--muted)] hover:text-[var(--foreground)]'}`}
                >
                    <User className="w-3.5 h-3.5" />
                    Layer A
                </button>
                <button
                    onClick={() => setActiveTab('layerB')}
                    className={`flex-1 py-2.5 text-xs font-medium flex items-center justify-center gap-1.5 transition-colors ${activeTab === 'layerB' ? 'text-violet-400 border-b-2 border-violet-500 bg-violet-500/5' : 'text-[var(--muted)] hover:text-[var(--foreground)]'}`}
                >
                    <Layers className="w-3.5 h-3.5" />
                    Layer B
                </button>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                {activeTab === 'status' && (
                    <div className="space-y-6 animate-fade-in">
                        <section className="space-y-3">
                            <h3 className="text-xs font-bold text-[var(--muted)] uppercase tracking-wider flex items-center gap-2">
                                <Info className="w-3.5 h-3.5" />
                                現在の構成
                            </h3>
                            <div className="grid gap-3">
                                {/* Layer 0 Summary */}
                                <div className="p-3 bg-[var(--background)] rounded-lg border border-[var(--border)]">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                                            <Shield className="w-3 h-3" />
                                            Layer 0: システム原則
                                        </span>
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${status.layer0?.file_exists ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                                            {status.layer0?.file_exists ? '常駐中' : '未設定'}
                                        </span>
                                    </div>
                                    <div className="text-[11px] text-[var(--muted)]">
                                        {status.layer0?.char_count.toLocaleString() || 0} 文字のプロンプトが全セッションに適用されています。
                                    </div>
                                </div>

                                {/* Layer A Summary */}
                                <div className="p-3 bg-[var(--background)] rounded-lg border border-[var(--border)]">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                                            <User className="w-3 h-3" />
                                            Layer A: 個人コンテキスト
                                        </span>
                                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary-500/10 text-primary-400">
                                            {status.layerA?.count || 0} 件有効
                                        </span>
                                    </div>
                                    <div className="text-[11px] text-[var(--muted)]">
                                        過去の判断基準や学びのうち、質問に関係するものが動的に抽出されます。
                                    </div>
                                </div>

                                {/* Layer B Summary */}
                                <div className="p-3 bg-[var(--background)] rounded-lg border border-[var(--border)]">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-xs font-bold text-violet-400 flex items-center gap-1.5">
                                            <Layers className="w-3 h-3" />
                                            Layer B: セッション文脈
                                        </span>
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${activeLayerB ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30' : 'bg-[var(--card)] text-[var(--muted)] border border-[var(--border)]'}`}>
                                            {activeLayerB ? '✅ 注入中' : '⚠ 未設定'}
                                        </span>
                                    </div>
                                    {activeLayerB ? (
                                        <div className="space-y-2">
                                            <div className="text-[11px] text-[var(--foreground)] font-medium truncate">
                                                ✨ {activeLayerBTitle}
                                            </div>
                                            <div className="text-[10px] text-[var(--muted)]">
                                                このセッションのユーザープロンプトに優先的に注入されています。
                                            </div>
                                            <button
                                                onClick={clearLayerB}
                                                className="text-[10px] text-red-400 hover:text-red-300 flex items-center gap-1"
                                            >
                                                <X className="w-2.5 h-2.5" />
                                                このセッションからクリア
                                            </button>
                                        </div>
                                    ) : (
                                        <div className="text-[11px] text-[var(--muted)]">
                                            手動入力またはMDファイルから生成した文脈を注入できます。
                                        </div>
                                    )}
                                </div>
                            </div>
                        </section>
                    </div>
                )}

                {activeTab === 'layer0' && (
                    <div className="space-y-4 animate-fade-in h-full flex flex-col">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold flex items-center gap-2">
                                <Shield className="w-4 h-4 text-amber-500" />
                                システム常設プロンプト
                            </h3>
                            <button
                                onClick={reloadLayer0}
                                disabled={layer0Loading}
                                className="p-1.5 hover:bg-white/5 rounded-lg text-[var(--muted)] transition-colors"
                                title="再読み込み"
                            >
                                <RefreshCw className={`w-3.5 h-3.5 ${layer0Loading ? 'animate-spin' : ''}`} />
                            </button>
                        </div>

                        <p className="text-[11px] text-[var(--muted)] leading-relaxed">
                            全てのAI回答のベースとなる原則（Layer 0）です。建築PM/CMとしての振る舞いや、法規・基準への参照方針を定義します。
                        </p>

                        <div className="flex-1 min-h-[300px] relative">
                            <textarea
                                value={layer0Text}
                                onChange={(e) => setLayer0Text(e.target.value)}
                                className="w-full h-full bg-[var(--background)] border border-[var(--border)] rounded-lg p-3 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-amber-500 resize-none custom-scrollbar"
                                placeholder="Layer 0 の内容を入力..."
                            />
                            <div className="absolute bottom-2 right-2 text-[10px] text-[var(--muted)] bg-[var(--card)]/80 px-1.5 py-0.5 rounded border border-[var(--border)]">
                                {layer0Text.length.toLocaleString()} chars
                            </div>
                        </div>

                        <button
                            onClick={saveLayer0}
                            disabled={layer0Saving}
                            className="w-full py-2.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold flex items-center justify-center gap-2 transition-all shadow-sm disabled:opacity-50"
                        >
                            {layer0Saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                            Layer 0 を保存して反映
                        </button>
                    </div>
                )}

                {activeTab === 'layerA' && (
                    <div className="space-y-4 animate-fade-in h-full flex flex-col">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold flex items-center gap-2">
                                <User className="w-4 h-4 text-emerald-500" />
                                蓄積済み Personal Contexts
                            </h3>
                            <span className="text-[10px] text-[var(--muted)] bg-[var(--background)] px-2 py-0.5 rounded-full border border-[var(--border)]">
                                {personalContexts.length} items
                            </span>
                        </div>

                        <p className="text-[11px] text-[var(--muted)] leading-relaxed">
                            AIがあなたの対話から抽出した「こだわり」や「判断基準」のリストです。
                        </p>

                        <div className="flex-1 space-y-3">
                            {personalContexts.length === 0 ? (
                                <div className="py-20 text-center space-y-2">
                                    <div className="w-12 h-12 bg-[var(--background)] rounded-full flex items-center justify-center mx-auto border border-[var(--border)] border-dashed">
                                        <User className="w-6 h-6 text-[var(--muted)] opacity-20" />
                                    </div>
                                    <p className="text-xs text-[var(--muted)]">まだデータがありません</p>
                                </div>
                            ) : (
                                personalContexts.map((ctx) => (
                                    <div key={ctx.id} className="group p-3 bg-[var(--background)] border border-[var(--border)] rounded-lg hover:border-emerald-500/30 transition-all">
                                        <div className="flex items-start justify-between mb-2">
                                            <div className="flex flex-wrap gap-1.5">
                                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold uppercase tracking-tight">
                                                    {ctx.type}
                                                </span>
                                                {ctx.project_tag && (
                                                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-primary-500/10 text-primary-400">
                                                        #{ctx.project_tag}
                                                    </span>
                                                )}
                                            </div>
                                            <button
                                                onClick={() => deletePersonalContext(ctx.id)}
                                                className="p-1 text-[var(--muted)] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                                            >
                                                <Trash2 className="w-3 h-3" />
                                            </button>
                                        </div>
                                        <p className="text-[11px] text-[var(--foreground)] leading-relaxed">
                                            {ctx.content}
                                        </p>
                                        {ctx.trigger_keywords.length > 0 && (
                                            <div className="mt-2 flex flex-wrap gap-1">
                                                {ctx.trigger_keywords.map((kw, i) => (
                                                    <span key={i} className="text-[9px] text-[var(--muted)] flex items-center gap-0.5">
                                                        <Check className="w-2 h-2 text-emerald-500" /> {kw}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                )}

                {activeTab === 'layerB' && (
                    <div className="space-y-4 animate-fade-in h-full flex flex-col">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold flex items-center gap-2">
                                <Layers className="w-4 h-4 text-violet-500" />
                                Session Context (Layer B)
                            </h3>
                            {activeLayerB && (
                                <button
                                    onClick={clearLayerB}
                                    className="text-[10px] text-red-400 hover:text-red-300 flex items-center gap-1"
                                >
                                    <X className="w-2.5 h-2.5" /> クリア
                                </button>
                            )}
                        </div>

                        {/* Sub Tabs */}
                        <div className="flex p-1 bg-[var(--background)] rounded-lg border border-[var(--border)]">
                            <button
                                onClick={() => setLayerBSubTab('text')}
                                className={`flex-1 py-1.5 text-[10px] font-bold rounded-md transition-all ${layerBSubTab === 'text' ? 'bg-violet-500 text-white shadow-sm' : 'text-[var(--muted)] hover:text-[var(--foreground)]'}`}
                            >
                                手動入力
                            </button>
                            <button
                                onClick={() => setLayerBSubTab('md')}
                                className={`flex-1 py-1.5 text-[10px] font-bold rounded-md transition-all ${layerBSubTab === 'md' ? 'bg-violet-500 text-white shadow-sm' : 'text-[var(--muted)] hover:text-[var(--foreground)]'}`}
                            >
                                MDから生成
                            </button>
                        </div>

                        {layerBSubTab === 'text' && (
                            <div className="space-y-3 flex-1 flex flex-col">
                                <div className="space-y-1.5">
                                    <label className="text-[10px] text-[var(--muted)] uppercase font-bold tracking-wider">タイトル</label>
                                    <input
                                        type="text"
                                        value={manualLayerBTitle}
                                        onChange={(e) => setManualLayerBTitle(e.target.value)}
                                        placeholder="例：基本設計の追加要望"
                                        className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs focus:ring-1 focus:ring-violet-500 focus:outline-none"
                                    />
                                </div>
                                <div className="space-y-1.5 flex-1 flex flex-col">
                                    <label className="text-[10px] text-[var(--muted)] uppercase font-bold tracking-wider">プロジェクト文脈</label>
                                    <textarea
                                        value={manualLayerBText}
                                        onChange={(e) => setManualLayerBText(e.target.value)}
                                        placeholder="現在のプロジェクトで考慮すべき独自の制約や前提条件を記入..."
                                        className="w-full flex-1 bg-[var(--background)] border border-[var(--border)] rounded-lg p-3 text-xs focus:ring-1 focus:ring-violet-500 focus:outline-none resize-none custom-scrollbar"
                                    />
                                </div>
                                <button
                                    onClick={applyManualLayerB}
                                    className="w-full py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-xs font-bold transition-all shadow-sm"
                                >
                                    このセッションに適用
                                </button>
                            </div>
                        )}

                        {layerBSubTab === 'md' && (
                            <div className="space-y-4 flex-1 overflow-y-auto custom-scrollbar pr-1">
                                {/* Generation Form */}
                                <div className="space-y-3 p-3 bg-[var(--background)] border border-[var(--border)] rounded-lg">
                                    <div className="grid grid-cols-2 gap-2">
                                        <div className="space-y-1">
                                            <label className="text-[9px] text-[var(--muted)] font-bold">モデル</label>
                                            <select
                                                value={selectedModel}
                                                onChange={(e) => setSelectedModel(e.target.value)}
                                                className="w-full bg-[var(--card)] border border-[var(--border)] rounded px-1.5 py-1 text-[10px]"
                                            >
                                                {Object.entries(availableModels).map(([k, v]) => (
                                                    <option key={k} value={k}>{v}</option>
                                                ))}
                                            </select>
                                        </div>
                                        <div className="space-y-1">
                                            <label className="text-[9px] text-[var(--muted)] font-bold">役割</label>
                                            <select
                                                value={selectedRole}
                                                onChange={(e) => setSelectedRole(e.target.value)}
                                                className="w-full bg-[var(--card)] border border-[var(--border)] rounded px-1.5 py-1 text-[10px]"
                                            >
                                                {Object.entries(availableRoles).map(([k, v]) => (
                                                    <option key={k} value={k}>{v}</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>

                                    <div className="space-y-1.5">
                                        <div className="flex items-center justify-between">
                                            <label className="text-[9px] text-[var(--muted)] font-bold">ファイル選択 ({selectedPaths.size})</label>
                                            <button onClick={fetchTree} className="p-0.5 hover:bg-white/5 rounded">
                                                <RefreshCw className={`w-2.5 h-2.5 ${treeLoading ? 'animate-spin' : ''}`} />
                                            </button>
                                        </div>
                                        <div className="max-h-32 overflow-y-auto border border-[var(--border)] bg-[var(--card)] rounded p-1">
                                            {tree ? (
                                                <MdTreeNode
                                                    node={tree}
                                                    level={0}
                                                    selectedPaths={selectedPaths}
                                                    onToggle={handleToggle}
                                                />
                                            ) : (
                                                <div className="py-4 text-center text-[10px] text-[var(--muted)]">No MD files</div>
                                            )}
                                        </div>
                                    </div>

                                    <button
                                        onClick={handleGenerateLayerB}
                                        disabled={selectedPaths.size === 0 || isGenerating}
                                        className="w-full py-2 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-700 hover:to-fuchsia-700 text-white text-[10px] font-bold rounded transition-all disabled:opacity-50"
                                    >
                                        {isGenerating ? '生成中...' : 'MDから文脈を生成'}
                                    </button>
                                </div>

                                {/* Saved Sheets */}
                                <div className="space-y-2">
                                    <h4 className="text-[10px] font-bold text-[var(--muted)] uppercase tracking-widest pl-1">保存済みシート</h4>
                                    {savedLoading ? (
                                        <div className="flex justify-center py-4"><Loader2 className="w-4 h-4 animate-spin text-violet-500" /></div>
                                    ) : savedSheets.length === 0 ? (
                                        <div className="text-[10px] text-[var(--muted)] text-center py-4 italic">No saved sheets</div>
                                    ) : (
                                        savedSheets.map(sheet => (
                                            <div key={sheet.id} className="group p-2 bg-[var(--background)] border border-[var(--border)] rounded-lg hover:border-violet-500/30 transition-all">
                                                <div className="flex items-center justify-between gap-2">
                                                    <div className="min-w-0 flex-1">
                                                        <div className="text-[11px] font-medium text-[var(--foreground)] truncate">{sheet.title || `Sheet #${sheet.id}`}</div>
                                                        <div className="text-[9px] text-[var(--muted)] flex items-center gap-2">
                                                            <span>{ROLE_LABELS[sheet.role] || sheet.role}</span>
                                                            <span>•</span>
                                                            <span>{sheet.file_count} files</span>
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-1">
                                                        <button
                                                            onClick={() => handleApplySavedSheet(sheet)}
                                                            className="px-2 py-0.5 bg-violet-500/10 text-violet-400 text-[10px] font-bold rounded border border-violet-500/20 hover:bg-violet-500 hover:text-white transition-all"
                                                        >
                                                            適用
                                                        </button>
                                                        <button
                                                            onClick={() => handleDeleteSavedSheet(sheet.id)}
                                                            className="p-1 text-[var(--muted)] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                                                        >
                                                            <Trash2 className="w-2.5 h-2.5" />
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Footer / Active Indicator */}
            <div className="p-2.5 bg-[var(--background)]/80 border-t border-[var(--border)] backdrop-blur-sm">
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${activeLayerB ? 'bg-violet-500 animate-pulse' : 'bg-[var(--border)]'}`} />
                    <div className="flex-1 min-w-0">
                        <div className="text-[10px] text-[var(--muted)] font-medium">Layer B (Manual Context)</div>
                        <div className={`text-[11px] truncate ${activeLayerB ? 'text-[var(--foreground)] font-bold' : 'text-[var(--muted)] italic'}`}>
                            {activeLayerB ? activeLayerBTitle : 'Not active in this session'}
                        </div>
                    </div>
                    {activeLayerB && (
                        <button
                            onClick={clearLayerB}
                            className="p-1 text-[var(--muted)] hover:text-red-400 transition-colors"
                            title="Clear session context"
                        >
                            <X className="w-3.5 h-3.5" />
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
