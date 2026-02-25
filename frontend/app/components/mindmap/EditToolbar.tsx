'use client';

import { Plus, Trash2, Undo2, Edit3, Eye, Search } from 'lucide-react';

interface Props {
    isEditMode: boolean;
    isProjectMode: boolean;
    onToggleEditMode: () => void;
    onAddNode: () => void;
    onDeleteNode: () => void;
    onUndo: () => void;
    onInvestigate: () => void;
    hasSelectedNode: boolean;
    canUndo: boolean;
}

export default function EditToolbar({
    isEditMode,
    isProjectMode,
    onToggleEditMode,
    onAddNode,
    onDeleteNode,
    onUndo,
    onInvestigate,
    hasSelectedNode,
    canUndo,
}: Props) {
    if (!isProjectMode) return null;

    return (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 bg-white border border-[var(--border)] rounded-xl shadow-lg px-2 py-1.5">
            {/* View/Edit Toggle */}
            <button
                onClick={(e) => { e.stopPropagation(); onToggleEditMode(); }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${isEditMode
                    ? 'bg-violet-100 text-violet-700 ring-1 ring-violet-300'
                    : 'bg-[var(--background)] text-[var(--muted)] hover:text-[var(--foreground)]'
                    }`}
            >
                {isEditMode ? (
                    <><Edit3 className="w-3.5 h-3.5" /> 編集中</>
                ) : (
                    <><Eye className="w-3.5 h-3.5" /> 閲覧</>
                )}
            </button>

            {isEditMode && (
                <>
                    <div className="w-px h-6 bg-[var(--border)] mx-1" />

                    <button
                        onClick={(e) => { e.stopPropagation(); onAddNode(); }}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs hover:bg-green-50 text-green-600 transition-colors"
                        title="ノード追加（ダイアログ）"
                    >
                        <Plus className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">追加</span>
                    </button>

                    <button
                        onClick={(e) => { e.stopPropagation(); onInvestigate(); }}
                        disabled={!hasSelectedNode}
                        className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors ${hasSelectedNode
                            ? 'hover:bg-indigo-50 text-indigo-600'
                            : 'text-[var(--muted)] opacity-40 cursor-not-allowed'
                            }`}
                        title="AI調査 (確認事項をリストアップ)"
                    >
                        <Search className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">調査</span>
                    </button>

                    <button
                        onClick={(e) => { e.stopPropagation(); onDeleteNode(); }}
                        disabled={!hasSelectedNode}
                        className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors ${hasSelectedNode
                            ? 'hover:bg-red-50 text-red-500'
                            : 'text-[var(--muted)] opacity-40 cursor-not-allowed'
                            }`}
                        title="ノード削除"
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">削除</span>
                    </button>

                    <div className="w-px h-6 bg-[var(--border)] mx-1" />

                    <button
                        onClick={(e) => { e.stopPropagation(); onUndo(); }}
                        disabled={!canUndo}
                        className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors ${canUndo
                            ? 'hover:bg-amber-50 text-amber-600'
                            : 'text-[var(--muted)] opacity-40 cursor-not-allowed'
                            }`}
                        title="元に戻す (Cmd+Z)"
                    >
                        <Undo2 className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">戻す</span>
                    </button>
                </>
            )}
        </div>
    );
}
