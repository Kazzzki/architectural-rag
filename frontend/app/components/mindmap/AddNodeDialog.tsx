'use client';

import { useState } from 'react';
import { X, Plus } from 'lucide-react';

const PHASES = ['基本計画', '基本設計', '実施設計', '施工準備', '施工'];
const CATEGORIES = ['構造', '意匠', '設備', '外装', '土木', '管理'];

interface Props {
    onAdd: (node: {
        label: string;
        description: string;
        phase: string;
        category: string;
        checklist: string[];
    }) => void;
    onClose: () => void;
}

export default function AddNodeDialog({ onAdd, onClose }: Props) {
    const [label, setLabel] = useState('');
    const [description, setDescription] = useState('');
    const [phase, setPhase] = useState(PHASES[0]);
    const [category, setCategory] = useState(CATEGORIES[0]);
    const [checklistInput, setChecklistInput] = useState('');
    const [checklist, setChecklist] = useState<string[]>([]);

    const addChecklistItem = () => {
        if (checklistInput.trim()) {
            setChecklist([...checklist, checklistInput.trim()]);
            setChecklistInput('');
        }
    };

    const handleSubmit = () => {
        if (!label.trim()) return;
        onAdd({ label, description, phase, category, checklist });
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
            onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-2xl shadow-2xl w-[480px] max-h-[80vh] overflow-y-auto">
                <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
                    <h3 className="text-lg font-bold flex items-center gap-2">
                        <Plus className="w-5 h-5 text-green-600" />
                        ノード追加
                    </h3>
                    <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--foreground)]">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-4 space-y-4">
                    <div>
                        <label className="block text-xs font-bold text-[var(--muted)] mb-1">ラベル *</label>
                        <input
                            type="text"
                            value={label}
                            onChange={(e) => setLabel(e.target.value)}
                            placeholder="例: 設備機器の選定"
                            className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-[var(--muted)] mb-1">説明</label>
                        <textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="ノードの詳細説明..."
                            rows={2}
                            className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 resize-none"
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-bold text-[var(--muted)] mb-1">フェーズ</label>
                            <select
                                value={phase}
                                onChange={(e) => setPhase(e.target.value)}
                                className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                            >
                                {PHASES.map(p => <option key={p} value={p}>{p}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-[var(--muted)] mb-1">カテゴリ</label>
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                            >
                                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-[var(--muted)] mb-1">チェックリスト</label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={checklistInput}
                                onChange={(e) => setChecklistInput(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && addChecklistItem()}
                                placeholder="項目を入力してEnter"
                                className="flex-1 bg-[var(--background)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-violet-500"
                            />
                            <button
                                onClick={addChecklistItem}
                                className="px-2 py-1.5 bg-violet-50 text-violet-600 rounded-lg text-xs hover:bg-violet-100 transition-colors"
                            >
                                追加
                            </button>
                        </div>
                        {checklist.length > 0 && (
                            <div className="mt-2 space-y-1">
                                {checklist.map((item, i) => (
                                    <div key={i} className="flex items-center justify-between text-xs bg-[var(--background)] rounded px-2 py-1">
                                        <span>{item}</span>
                                        <button
                                            onClick={() => setChecklist(checklist.filter((_, j) => j !== i))}
                                            className="text-red-500 hover:text-red-600"
                                        >
                                            <X className="w-3 h-3" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                <div className="p-4 border-t border-[var(--border)] flex justify-end gap-2">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                    >
                        キャンセル
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={!label.trim()}
                        className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors ${label.trim()
                            ? 'bg-violet-500 text-white hover:bg-violet-600'
                            : 'bg-[var(--border)] text-[var(--muted)] cursor-not-allowed'
                            }`}
                    >
                        追加する
                    </button>
                </div>
            </div>
        </div>
    );
}
