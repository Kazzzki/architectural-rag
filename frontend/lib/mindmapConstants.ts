export type CategoryDef = {
    key: string;
    label: string;
    color: string;
    order?: number;
};

export const CATEGORY_COLORS: Record<string, string> = {
    '構造': '#ef4444',
    '意匠': '#3b82f6',
    '設備': '#22c55e',
    '外装': '#f59e0b',
    '土木': '#8b5cf6',
    '管理': '#6b7280',
};

export const PHASES = ['基本計画', '基本設計', '実施設計', '施工準備', '施工'];

export const CATEGORIES = ['構造', '意匠', '設備', '外装', '土木', '管理'];

export const CATEGORY_LIST: CategoryDef[] = CATEGORIES.map((cat, index) => ({
    key: cat,
    label: cat,
    color: CATEGORY_COLORS[cat],
    order: index,
}));
