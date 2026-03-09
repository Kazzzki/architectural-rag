'use client';

import React from 'react';
import { X, Filter } from 'lucide-react';

interface Props {
    phases: string[];
    categories: string[];
    selectedPhases: Set<string>;
    selectedCategories: Set<string>;
    onTogglePhase: (phase: string) => void;
    onToggleCategory: (category: string) => void;
    onClearAll: () => void;
    categoryColors: Record<string, string>;
}

export default function FilterPanel({
    phases,
    categories,
    selectedPhases,
    selectedCategories,
    onTogglePhase,
    onToggleCategory,
    onClearAll,
    categoryColors
}: Props) {
    const hasFilters = selectedPhases.size > 0 || selectedCategories.size > 0;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium">
                    <Filter className="w-4 h-4 text-violet-600" />
                    <span>フィルター</span>
                </div>
                {hasFilters && (
                    <button
                        onClick={onClearAll}
                        className="text-[10px] text-violet-600 hover:text-violet-800 underline"
                    >
                        全てクリア
                    </button>
                )}
            </div>

            <div className="space-y-4">
                <section>
                    <h4 className="text-[10px] font-bold text-[var(--muted)] uppercase tracking-wider mb-2">フェーズ</h4>
                    <div className="flex flex-wrap gap-1.5">
                        {phases.map(phase => {
                            const isSelected = selectedPhases.has(phase);
                            return (
                                <button
                                    key={phase}
                                    onClick={() => onTogglePhase(phase)}
                                    className={`px-2.5 py-1 rounded-full text-[10px] font-medium transition-all border ${isSelected
                                        ? 'bg-violet-600 border-violet-600 text-white shadow-sm'
                                        : 'bg-white border-[var(--border)] text-[var(--muted)] hover:border-violet-300 hover:text-violet-600'
                                        }`}
                                >
                                    {phase}
                                </button>
                            );
                        })}
                    </div>
                </section>

                <section>
                    <h4 className="text-[10px] font-bold text-[var(--muted)] uppercase tracking-wider mb-2">カテゴリ</h4>
                    <div className="flex flex-wrap gap-1.5">
                        {categories.map(cat => {
                            const isSelected = selectedCategories.has(cat);
                            const color = categoryColors[cat] || '#6b7280';
                            return (
                                <button
                                    key={cat}
                                    onClick={() => onToggleCategory(cat)}
                                    className={`px-2.5 py-1 rounded-full text-[10px] font-medium transition-all border flex items-center gap-1.5 ${isSelected
                                        ? 'border-transparent text-white shadow-sm'
                                        : 'bg-white border-[var(--border)] text-[var(--muted)] hover:border-slate-300'
                                        }`}
                                    style={{
                                        backgroundColor: isSelected ? color : undefined,
                                        borderColor: isSelected ? color : undefined,
                                    }}
                                >
                                    <div
                                        className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-white' : ''}`}
                                        style={{ backgroundColor: isSelected ? undefined : color }}
                                    />
                                    {cat}
                                </button>
                            );
                        })}
                    </div>
                </section>
            </div>
        </div>
    );
}
