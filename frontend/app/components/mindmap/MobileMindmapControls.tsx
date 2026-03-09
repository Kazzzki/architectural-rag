'use client';

import React, { useState } from 'react';
import { Search, Filter, ListChecks, X, ChevronRight } from 'lucide-react';
import FilterPanel from './FilterPanel';
import GoalSearchBar from './GoalSearchBar';

interface Props {
    nodes: any[];
    nextActions: any[];
    phases: string[];
    categories: string[];
    selectedPhases: Set<string>;
    selectedCategories: Set<string>;
    onTogglePhase: (phase: string) => void;
    onToggleCategory: (category: string) => void;
    onClearFilters: () => void;
    categoryColors: Record<string, string>;
    templateId: string;
    highlightedCount: number;
    onReverseTreeResult: (nodeIds: string[], edgeIds: string[]) => void;
    onNodeSelect: (nodeId: string) => void;
    onClearSearch: () => void;
}

type MobileMenu = 'none' | 'search' | 'filter' | 'tasks';

export default function MobileMindmapControls({
    nodes,
    nextActions,
    phases,
    categories,
    selectedPhases,
    selectedCategories,
    onTogglePhase,
    onToggleCategory,
    onClearFilters,
    categoryColors,
    templateId,
    highlightedCount,
    onReverseTreeResult,
    onNodeSelect,
    onClearSearch
}: Props) {
    const [activeMenu, setActiveMenu] = useState<MobileMenu>('none');

    const closeMenu = () => setActiveMenu('none');

    const renderOverlay = () => {
        if (activeMenu === 'none') return null;

        return (
            <div className="fixed inset-0 z-[60] flex flex-col bg-black/40 backdrop-blur-sm animate-fade-in md:hidden">
                <div className="mt-auto bg-white rounded-t-2xl shadow-2xl max-h-[85vh] flex flex-col animate-slide-up">
                    <div className="flex items-center justify-between p-4 border-b border-slate-100">
                        <h3 className="font-bold text-slate-800 flex items-center gap-2">
                            {activeMenu === 'search' && <><Search className="w-4 h-4 text-violet-600" /> ゴール逆引き検索</>}
                            {activeMenu === 'filter' && <><Filter className="w-4 h-4 text-violet-600" /> フィルター</>}
                            {activeMenu === 'tasks' && <><ListChecks className="w-4 h-4 text-violet-600" /> 次の決定事項</>}
                        </h3>
                        <button onClick={closeMenu} className="p-2 text-slate-400 hover:text-slate-600">
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto p-4 pb-10">
                        {activeMenu === 'search' && (
                            <GoalSearchBar
                                nodes={nodes}
                                onSearch={(id) => { onNodeSelect(id); closeMenu(); }}
                                onClear={onClearSearch}
                                highlightedCount={highlightedCount}
                                templateId={templateId}
                                onReverseTreeResult={(n, e) => { onReverseTreeResult(n, e); closeMenu(); }}
                            />
                        )}
                        {activeMenu === 'filter' && (
                            <FilterPanel
                                phases={phases}
                                categories={categories}
                                selectedPhases={selectedPhases}
                                selectedCategories={selectedCategories}
                                onTogglePhase={onTogglePhase}
                                onToggleCategory={onToggleCategory}
                                onClearAll={onClearFilters}
                                categoryColors={categoryColors}
                            />
                        )}
                        {activeMenu === 'tasks' && (
                            <div className="space-y-2">
                                {nextActions.length === 0 && (
                                    <div className="py-10 text-center text-slate-400 text-sm">
                                        現在のフェーズでは決定事項はありません
                                    </div>
                                )}
                                {nextActions.map(action => (
                                    <button
                                        key={action.node_id}
                                        onClick={() => { onNodeSelect(action.node_id); closeMenu(); }}
                                        className="w-full flex items-center justify-between p-3 rounded-xl border border-slate-100 bg-slate-50 hover:bg-white hover:shadow-sm transition-all"
                                    >
                                        <div className="text-left min-w-0">
                                            <span className="text-sm font-bold text-slate-700 block truncate">{action.label}</span>
                                            <span className="text-[10px] text-slate-400">{action.phase} / {action.category}</span>
                                        </div>
                                        <ChevronRight className="w-4 h-4 text-slate-300" />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    };

    return (
        <>
            {renderOverlay()}

            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 p-1 bg-white/90 backdrop-blur border border-slate-200 rounded-2xl shadow-2xl md:hidden">
                <button
                    onClick={() => setActiveMenu('search')}
                    className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all ${activeMenu === 'search' ? 'bg-violet-600 text-white shadow-inner' : 'text-slate-500 hover:bg-slate-50'
                        }`}
                >
                    <Search className="w-5 h-5" />
                    <span className="text-[9px] font-bold">検索</span>
                </button>
                <button
                    onClick={() => setActiveMenu('filter')}
                    className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all ${activeMenu === 'filter' ? 'bg-violet-600 text-white shadow-inner' : 'text-slate-500 hover:bg-slate-50'
                        }`}
                >
                    <Filter className="w-5 h-5" />
                    <span className="text-[9px] font-bold">フィルタ</span>
                </button>
                <div className="w-px h-8 bg-slate-200 mx-1" />
                <button
                    onClick={() => setActiveMenu('tasks')}
                    className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all ${activeMenu === 'tasks' ? 'bg-violet-600 text-white shadow-inner' : 'text-slate-500 hover:bg-slate-50'
                        }`}
                >
                    <div className="relative">
                        <ListChecks className="w-5 h-5" />
                        {nextActions.length > 0 && (
                            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-amber-500 border-2 border-white rounded-full" />
                        )}
                    </div>
                    <span className="text-[9px] font-bold">タスク</span>
                </button>
            </div>
        </>
    );
}
