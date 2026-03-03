'use client';

/**
 * ContextSheetPanel.tsx
 * 折りたたみ式コンテキスト設定パネル
 * - 新規生成タブ：ファイルツリー（MDのみ）・モデル/役割/文字数設定・シート生成
 * - 保存済みタブ：一覧表示・適用・削除
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    Sparkles,
    ChevronDown,
    ChevronRight,
    Folder,
    FileText,
    Loader2,
    RefreshCw,
    Trash2,
    Check,
    X,
    Settings,
    Clock,
    Files,
} from 'lucide-react';
import { authFetch, API_BASE, contextSheetStream, listContextSheets, deleteContextSheet } from '@/lib/api';
import type { ContextSheetSummary, StreamUpdate } from '@/lib/api';

// ===== ファイルツリー型（Library.tsx と共通定義） =====
interface FileNode {
    name: string;
    type: 'directory' | 'file';
    path: string;
    children?: FileNode[];
    size?: number;
    ocr_status?: string;
}

// ===== Props =====
interface ContextSheetPanelProps {
    availableModels: Record<string, string>;
    availableRoles: Record<string, string>;
    activeContextSheet: string | null;
    activeSheetTitle: string | null;
    activeContextRole: string | null;
    onSheetApplied: (content: string, title: string, role: string) => void;
    onSheetCleared: () => void;
    onStreamStart: () => void;
    onStreamChunk: (chunk: string) => void;
    onStreamEnd: () => void;
    isStreaming: boolean;
}

// ===== ロールラベル =====
const ROLE_LABELS: Record<string, string> = {
    pmcm: 'PMCM',
    designer: '設計者',
    cost: 'コスト管理者',
};

// ===== MDファイルツリーコンポーネント =====
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

    // Mdのみフィルタリングしたchildrenを持つ
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

    // Directory node — only render if it has any MD descendants
    const hasMd = (n: FileNode): boolean =>
        n.type === 'file' ? n.name.endsWith('.md') : (n.children?.some(hasMd) ?? false);
    if (!hasMd(node)) return null;

    // Folder check states
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
                <span className="text-[10px] text-[var(--muted)] ml-1">({allMdInFolder.length} MD)</span>
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

// ===== メインコンポーネント =====
export default function ContextSheetPanel({
    availableModels,
    availableRoles,
    activeContextSheet,
    activeSheetTitle,
    activeContextRole,
    onSheetApplied,
    onSheetCleared,
    onStreamStart,
    onStreamChunk,
    onStreamEnd,
    isStreaming,
}: ContextSheetPanelProps) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [activeTab, setActiveTab] = useState<'generate' | 'saved'>('generate');

    // 生成フォーム state
    const [selectedModel, setSelectedModel] = useState(
        Object.keys(availableModels)[0] || 'gemini-3-flash-preview'
    );
    const [selectedRole, setSelectedRole] = useState(
        Object.keys(availableRoles)[0] || 'pmcm'
    );
    const [charLimit, setCharLimit] = useState(80000);
    const [sheetTitle, setSheetTitle] = useState('');
    const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());

    // ファイルツリー state
    const [tree, setTree] = useState<FileNode | null>(null);
    const [treeLoading, setTreeLoading] = useState(false);
    const [treeError, setTreeError] = useState<string | null>(null);

    // 保存済みシート state
    const [savedSheets, setSavedSheets] = useState<ContextSheetSummary[]>([]);
    const [savedLoading, setSavedLoading] = useState(false);
    const [deletingId, setDeletingId] = useState<number | null>(null);
    const [applyingId, setApplyingId] = useState<number | null>(null);

    const [isGenerating, setIsGenerating] = useState(false);

    // モデルが外部から変わったとき同期
    useEffect(() => {
        const keys = Object.keys(availableModels);
        if (keys.length > 0 && !availableModels[selectedModel]) {
            setSelectedModel(keys[0]);
        }
    }, [availableModels]);

    useEffect(() => {
        const keys = Object.keys(availableRoles);
        if (keys.length > 0 && !availableRoles[selectedRole]) {
            setSelectedRole(keys[0]);
        }
    }, [availableRoles]);

    const fetchTree = useCallback(async () => {
        setTreeLoading(true);
        setTreeError(null);
        try {
            const res = await authFetch(`${API_BASE}/api/files/tree`);
            if (res.ok) {
                setTree(await res.json());
            } else {
                setTreeError(`ファイル一覧の取得に失敗しました (HTTP ${res.status})`);
            }
        } catch (e: any) {
            console.error('tree fetch error', e);
            setTreeError('ファイル一覧を取得できません。バックエンドに接続できるか確認してください。');
        } finally {
            setTreeLoading(false);
        }
    }, []);

    const fetchSaved = useCallback(async () => {
        setSavedLoading(true);
        try {
            const sheets = await listContextSheets();
            setSavedSheets(sheets);
        } catch (e) {
            console.error('list sheets error', e);
        } finally {
            setSavedLoading(false);
        }
    }, []);

    // パネル展開時にツリーとシート一覧を取得
    useEffect(() => {
        if (isExpanded) {
            if (!tree) fetchTree();
        }
    }, [isExpanded, tree, fetchTree]);

    useEffect(() => {
        if (isExpanded && activeTab === 'saved') fetchSaved();
    }, [isExpanded, activeTab, fetchSaved]);

    // チェックボックストグル（再帰対応）
    const handleToggle = useCallback((node: FileNode, checked: boolean) => {
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
    }, []);

    const handleGenerate = async () => {
        if (selectedPaths.size === 0 || isGenerating || isStreaming) return;
        setIsGenerating(true);
        onStreamStart();
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
                    onStreamChunk(update.data);
                } else if (update.type === 'truncation_warning') {
                    onStreamChunk(update.data);
                } else if (update.type === 'saved') {
                    // シート保存完了: 保存済み一覧更新 & 自動適用
                    fetchSaved();
                    onSheetApplied(
                        accumulated,
                        sheetTitle.trim() || `シート #${update.id}`,
                        selectedRole,
                    );
                }
            }
        } catch (err: any) {
            onStreamChunk(`\n\n⚠️ 生成エラー: ${err.message}`);
        } finally {
            setIsGenerating(false);
            onStreamEnd();
        }
    };

    const handleDelete = async (id: number) => {
        setDeletingId(id);
        try {
            await deleteContextSheet(id);
            setSavedSheets((prev) => prev.filter((s) => s.id !== id));
        } catch (e) {
            console.error('delete error', e);
        } finally {
            setDeletingId(null);
        }
    };

    const handleApply = async (sheet: ContextSheetSummary) => {
        setApplyingId(sheet.id);
        try {
            const { getContextSheet } = await import('@/lib/api');
            const detail = await getContextSheet(sheet.id);
            if (detail.content) {
                onSheetApplied(detail.content, sheet.title || `シート #${sheet.id}`, sheet.role);
            }
        } catch (e) {
            console.error('apply error', e);
        } finally {
            setApplyingId(null);
        }
    };

    const roleLabel = (role: string) => ROLE_LABELS[role] || role;
    const formatDate = (iso: string) => {
        try { return new Date(iso).toLocaleString('ja-JP', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
        catch { return iso; }
    };

    return (
        <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            {/* Header / Toggle */}
            <button
                type="button"
                onClick={() => setIsExpanded((v) => !v)}
                className="w-full flex items-center gap-2 px-4 py-2.5 bg-[var(--background)] hover:bg-white/5 transition-colors text-sm"
            >
                <Settings className="w-3.5 h-3.5 text-violet-400" />
                <span className="font-medium text-[var(--foreground)]">コンテキスト設定</span>

                {/* Active indicator */}
                {activeContextSheet && (
                    <div className="flex items-center gap-1.5 ml-2 px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-500/30 text-xs">
                        <Sparkles className="w-2.5 h-2.5 text-violet-400" />
                        <span className="text-violet-300 truncate max-w-[180px]">
                            {activeSheetTitle || roleLabel(activeContextRole || '')}
                        </span>
                        <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); onSheetCleared(); }}
                            className="text-violet-400 hover:text-violet-200 ml-0.5"
                        >
                            <X className="w-3 h-3" />
                        </button>
                    </div>
                )}
                <ChevronDown
                    className={`w-3.5 h-3.5 text-[var(--muted)] ml-auto transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                />
            </button>

            {/* Expanded panel */}
            {isExpanded && (
                <div className="border-t border-[var(--border)] bg-[var(--background)]/50">
                    {/* Tabs */}
                    <div className="flex border-b border-[var(--border)]">
                        {(['generate', 'saved'] as const).map((tab) => (
                            <button
                                key={tab}
                                type="button"
                                onClick={() => setActiveTab(tab)}
                                className={`px-4 py-2 text-xs font-medium transition-colors ${activeTab === tab
                                    ? 'border-b-2 border-violet-500 text-violet-300'
                                    : 'text-[var(--muted)] hover:text-[var(--foreground)]'
                                    }`}
                            >
                                {tab === 'generate' ? '✨ 新規生成' : `📋 保存済み (${savedSheets.length})`}
                            </button>
                        ))}
                    </div>

                    {/* TAB: Generate */}
                    {activeTab === 'generate' && (
                        <div className="p-4 space-y-4">
                            {/* Controls row */}
                            <div className="flex flex-wrap gap-3 items-end">
                                {/* Model */}
                                <div className="flex flex-col gap-1">
                                    <label className="text-[10px] text-[var(--muted)] uppercase tracking-wider">モデル</label>
                                    <div className="relative">
                                        <select
                                            value={selectedModel}
                                            onChange={(e) => setSelectedModel(e.target.value)}
                                            className="bg-[var(--background)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs appearance-none pr-6 focus:outline-none focus:ring-1 focus:ring-violet-500"
                                        >
                                            {Object.entries(availableModels).length > 0
                                                ? Object.entries(availableModels).map(([k, v]) => (
                                                    <option key={k} value={k}>{v}</option>
                                                ))
                                                : <option value="gemini-3-flash-preview">Gemini 3 Flash</option>
                                            }
                                        </select>
                                        <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--muted)] pointer-events-none" />
                                    </div>
                                </div>

                                {/* Role */}
                                <div className="flex flex-col gap-1">
                                    <label className="text-[10px] text-[var(--muted)] uppercase tracking-wider">役割</label>
                                    <div className="relative">
                                        <select
                                            value={selectedRole}
                                            onChange={(e) => setSelectedRole(e.target.value)}
                                            className="bg-[var(--background)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs appearance-none pr-6 focus:outline-none focus:ring-1 focus:ring-violet-500"
                                        >
                                            {Object.entries(availableRoles).length > 0
                                                ? Object.entries(availableRoles).map(([k, v]) => (
                                                    <option key={k} value={k}>{v}</option>
                                                ))
                                                : <>
                                                    <option value="pmcm">PMCM</option>
                                                    <option value="designer">設計者</option>
                                                    <option value="cost">コスト管理者</option>
                                                </>
                                            }
                                        </select>
                                        <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--muted)] pointer-events-none" />
                                    </div>
                                </div>

                                {/* Char limit */}
                                <div className="flex flex-col gap-1">
                                    <label className="text-[10px] text-[var(--muted)] uppercase tracking-wider">文字数上限</label>
                                    <input
                                        type="number"
                                        value={charLimit}
                                        onChange={(e) => setCharLimit(Math.max(1000, parseInt(e.target.value) || 80000))}
                                        min={1000}
                                        max={500000}
                                        step={10000}
                                        className="w-24 bg-[var(--background)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500"
                                    />
                                </div>

                                {/* Title */}
                                <div className="flex flex-col gap-1 flex-1 min-w-[140px]">
                                    <label className="text-[10px] text-[var(--muted)] uppercase tracking-wider">タイトル（任意）</label>
                                    <input
                                        type="text"
                                        value={sheetTitle}
                                        onChange={(e) => setSheetTitle(e.target.value)}
                                        placeholder="例：2階平面図セット分析"
                                        className="bg-[var(--background)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500 placeholder:text-[var(--muted)]"
                                    />
                                </div>
                            </div>

                            {/* File tree */}
                            <div>
                                <div className="flex items-center justify-between mb-1.5">
                                    <span className="text-[10px] text-[var(--muted)] uppercase tracking-wider">
                                        対象MDファイル選択
                                        {selectedPaths.size > 0 && (
                                            <span className="ml-2 text-violet-400 font-semibold">{selectedPaths.size}件選択中</span>
                                        )}
                                    </span>
                                    <div className="flex items-center gap-2">
                                        {selectedPaths.size > 0 && (
                                            <button
                                                type="button"
                                                onClick={() => setSelectedPaths(new Set())}
                                                className="text-[10px] text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                                            >
                                                全解除
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            onClick={fetchTree}
                                            className="p-0.5 hover:text-[var(--foreground)] text-[var(--muted)] transition-colors"
                                            title="更新"
                                        >
                                            <RefreshCw className={`w-3 h-3 ${treeLoading ? 'animate-spin' : ''}`} />
                                        </button>
                                    </div>
                                </div>
                                <div className="border border-[var(--border)] rounded-lg bg-[var(--background)] overflow-y-auto max-h-48 p-1">
                                    {treeLoading ? (
                                        <div className="flex items-center justify-center py-6 text-[var(--muted)]">
                                            <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                            <span className="text-xs">読み込み中...</span>
                                        </div>
                                    ) : treeError ? (
                                        <div className="py-4 px-3 text-center space-y-1">
                                            <p className="text-xs text-red-400">{treeError}</p>
                                            <p className="text-[10px] text-[var(--muted)]">Driveから同期するか、ファイルをアップロードしてください。</p>
                                            <button type="button" onClick={fetchTree} className="text-[10px] text-violet-400 hover:text-violet-300 underline mt-1">再試行</button>
                                        </div>
                                    ) : tree ? (
                                        <MdTreeNode node={tree} level={0} selectedPaths={selectedPaths} onToggle={handleToggle} />
                                    ) : (
                                        <div className="py-6 text-center text-xs text-[var(--muted)]">MDファイルが見つかりません。Driveから同期してください。</div>
                                    )}
                                </div>
                            </div>

                            {/* Generate button */}
                            <button
                                type="button"
                                onClick={handleGenerate}
                                disabled={selectedPaths.size === 0 || isGenerating || isStreaming}
                                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-700 hover:to-fuchsia-700 text-white text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                                {isGenerating
                                    ? <><Loader2 className="w-4 h-4 animate-spin" /> 生成中...</>
                                    : <><Sparkles className="w-4 h-4" /> コンテキストシートを生成 ({selectedPaths.size}件のMD)</>
                                }
                            </button>
                        </div>
                    )}

                    {/* TAB: Saved sheets */}
                    {activeTab === 'saved' && (
                        <div className="p-3 space-y-2">
                            {savedLoading ? (
                                <div className="flex items-center justify-center py-6 text-[var(--muted)]">
                                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                    <span className="text-xs">読み込み中...</span>
                                </div>
                            ) : savedSheets.length === 0 ? (
                                <div className="py-6 text-center text-xs text-[var(--muted)]">
                                    保存済みシートはありません。「新規生成」タブから作成してください。
                                </div>
                            ) : (
                                savedSheets.map((sheet) => (
                                    <div
                                        key={sheet.id}
                                        className="flex items-start gap-3 p-3 rounded-lg border border-[var(--border)] hover:border-violet-500/40 transition-colors group"
                                    >
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="text-xs font-medium text-[var(--foreground)] truncate">
                                                    {sheet.title || `シート #${sheet.id}`}
                                                </span>
                                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-500/15 text-violet-300 flex-shrink-0">
                                                    {roleLabel(sheet.role)}
                                                </span>
                                                {sheet.truncated && (
                                                    <span className="text-[10px] text-yellow-400 flex-shrink-0" title="文字数上限により一部省略">⚠️ 省略あり</span>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-3 text-[10px] text-[var(--muted)]">
                                                <span className="flex items-center gap-1">
                                                    <Files className="w-2.5 h-2.5" /> {sheet.file_count}件のMD
                                                </span>
                                                <span className="flex items-center gap-1">
                                                    <Clock className="w-2.5 h-2.5" /> {formatDate(sheet.created_at)}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-1.5 flex-shrink-0">
                                            <button
                                                type="button"
                                                onClick={() => handleApply(sheet)}
                                                disabled={applyingId === sheet.id}
                                                className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-violet-600/20 hover:bg-violet-600/40 text-violet-300 text-xs font-medium transition-colors disabled:opacity-50"
                                            >
                                                {applyingId === sheet.id
                                                    ? <Loader2 className="w-3 h-3 animate-spin" />
                                                    : <Check className="w-3 h-3" />
                                                }
                                                適用
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => handleDelete(sheet.id)}
                                                disabled={deletingId === sheet.id}
                                                className="p-1 rounded-md text-[var(--muted)] hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                                                title="削除"
                                            >
                                                {deletingId === sheet.id
                                                    ? <Loader2 className="w-3 h-3 animate-spin" />
                                                    : <Trash2 className="w-3 h-3" />
                                                }
                                            </button>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
