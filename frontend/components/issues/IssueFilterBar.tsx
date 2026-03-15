'use client';

import React from 'react';

export type PriorityFilter = 'all' | 'critical' | 'normal_up';

interface IssueFilterBarProps {
  priorityFilter: PriorityFilter;
  onPriorityFilter: (f: PriorityFilter) => void;
  categoryFilter: string;
  onCategoryFilter: (c: string) => void;
}

const CATEGORIES = ['全カテゴリ', '工程', 'コスト', '品質', '安全'];

export default function IssueFilterBar({
  priorityFilter,
  onPriorityFilter,
  categoryFilter,
  onCategoryFilter,
}: IssueFilterBarProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-gray-50 flex-wrap">
      {/* 重要度フィルター */}
      <div className="flex gap-1">
        {([
          ['all', '全表示'],
          ['normal_up', 'Normal以上'],
          ['critical', 'Criticalのみ'],
        ] as [PriorityFilter, string][]).map(([val, label]) => (
          <button
            key={val}
            onClick={() => onPriorityFilter(val)}
            className={`text-xs px-3 py-1 rounded-full border transition-colors ${
              priorityFilter === val
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-100'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* カテゴリフィルター */}
      <select
        value={categoryFilter}
        onChange={(e) => onCategoryFilter(e.target.value)}
        className="text-sm border border-gray-300 rounded px-2 py-1 bg-white"
      >
        {CATEGORIES.map((c) => (
          <option key={c} value={c === '全カテゴリ' ? '' : c}>{c}</option>
        ))}
      </select>
    </div>
  );
}
