'use client';

import { Plus, Trash2, Undo2, Edit3, Eye, Search, CheckCircle2, Circle } from 'lucide-react';

interface Props {
    isEditMode: boolean;
    isProjectMode: boolean;
    onToggleEditMode: () => void;
    onAddNode: () => void;
    onDeleteNode: () => void;
    onUndo: () => void;
    onInvestigate: () => void;
    onBatchStatusChange: (status: string) => void;
    hasSelectedNode: boolean;
    selectedCount: number;
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
    onBatchStatusChange,
    hasSelectedNode,
    selectedCount,
    canUndo,
}: Props) {
    if (!isProjectMode) return null;

    return (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 bg-white/90 backdrop-blur-md border border-[var(--border)] rounded-xl shadow-xl px-2 py-1.5 transition-all">
            {/* View/Edit Toggle */}
            <button
                onClick={(e) => { e.stopPropagation(); onToggleEditMode(); }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${isEditMode
                    ? 'bg-violet-600 text-white shadow-md'
                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                    }`}
            >
                {isEditMode ? (
                    <><Edit3 className="w-3.5 h-3.5" /> 編集モード</>
                ) : (
                    <><Eye className="w-3.5 h-3.5" /> 閲覧モード</>
                )}
            </button>

            {isEditMode && (
                <>
                    <div className="w-px h-6 bg-slate-200 mx-1" />

                    <button
                        onClick={(e) => { e.stopPropagation(); onAddNode(); }}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs hover:bg-green-50 text-green-600 transition-colors font-medium"
                        title="ノード追加"
                    >
                        <Plus className="w-4 h-4" />
                        <span className="hidden lg:inline">追加</span>
                    </button>

                    <div className="w-px h-6 bg-slate-200 mx-1" />

                    {/* Selection specific actions */}
                    <div className="flex items-center gap-1">
                        {selectedCount > 1 && (
                            <span className="text-[10px] font-bold bg-violet-100 text-violet-600 px-2 py-1 rounded-full mr-1">
                                {selectedCount} 選択中
                            </span>
                        )}

                        <button
                            onClick={(e) => { e.stopPropagation(); onInvestigate(); }}
                            disabled={!hasSelectedNode}
                            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors font-medium ${hasSelectedNode
                                ? 'hover:bg-indigo-50 text-indigo-600'
                                : 'text-slate-300 opacity-40 cursor-not-allowed'
                                }`}
                            title="AI調査"
                        >
                            <Search className="w-3.5 h-3.5" />
                            <span className="hidden lg:inline">調査</span>
                        </button>

                        {selectedCount > 0 && (
                            <>
                                <button
                                    onClick={(e) => { e.stopPropagation(); onBatchStatusChange('todo'); }}
                                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs hover:bg-slate-100 text-slate-600 transition-colors font-medium"
                                    title="一括未完了"
                                >
                                    <Circle className="w-3.5 h-3.5" />
                                    <span className="hidden lg:inline">未完了</span>
                                </button>
                                <button
                                    onClick={(e) => { e.stopPropagation(); onBatchStatusChange('done'); }}
                                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs hover:bg-emerald-50 text-emerald-600 transition-colors font-medium"
                                    title="一括完了"
                                >
                                    <CheckCircle2 className="w-3.5 h-3.5" />
                                    <span className="hidden lg:inline">完了</span>
                                </button>
                            </>
                        )}

                        <button
                            onClick={(e) => { e.stopPropagation(); onDeleteNode(); }}
                            disabled={!hasSelectedNode}
                            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors font-medium ${hasSelectedNode
                                ? 'hover:bg-red-50 text-red-500'
                                : 'text-slate-300 opacity-40 cursor-not-allowed'
                                }`}
                            title={selectedCount > 1 ? "一括削除" : "削除"}
                        >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span className="hidden lg:inline">{selectedCount > 1 ? '一括削除' : '削除'}</span>
                        </button>
                    </div>

                    <div className="w-px h-6 bg-slate-200 mx-1" />

                    <button
                        onClick={(e) => { e.stopPropagation(); onUndo(); }}
                        disabled={!canUndo}
                        className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors font-medium ${canUndo
                            ? 'hover:bg-amber-50 text-amber-600'
                            : 'text-slate-300 opacity-40 cursor-not-allowed'
                            }`}
                        title="元に戻す (Cmd+Z)"
                    >
                        <Undo2 className="w-3.5 h-3.5" />
                        <span className="hidden lg:inline">戻す</span>
                    </button>
                </>
            )}
        </div>
    );
}
