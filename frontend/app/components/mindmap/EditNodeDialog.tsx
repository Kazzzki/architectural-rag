'use client';

import { useState, useEffect } from 'react';
import { X, Edit2, Save } from 'lucide-react';
import { PHASES, CATEGORIES } from '@/lib/mindmapConstants';

interface ProcessNode {
    id: string;
    label: string;
    description: string;
    phase: string;
    category: string;
    checklist: string[];
}

interface Props {
    node: ProcessNode;
    onSave: (nodeId: string, updates: Partial<ProcessNode>) => void;
    onClose: () => void;
}

export default function EditNodeDialog({ node, onSave, onClose }: Props) {
    const [label, setLabel] = useState(node.label);
    const [description, setDescription] = useState(node.description || '');
    const [phase, setPhase] = useState(node.phase);
    const [category, setCategory] = useState(node.category);
    const [checklistInput, setChecklistInput] = useState('');
    const [checklist, setChecklist] = useState<string[]>(node.checklist || []);

    const addChecklistItem = () => {
        if (checklistInput.trim()) {
            setChecklist([...checklist, checklistInput.trim()]);
            setChecklistInput('');
        }
    };

    const handleSave = () => {
        if (!label.trim()) return;
        onSave(node.id, {
            label,
            description,
            phase,
            category,
            checklist
        });
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
            onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-2xl shadow-2xl w-[480px] max-h-[80vh] overflow-y-auto">
                <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
                    <h3 className="text-lg font-bold flex items-center gap-2">
                        <Edit2 className="w-5 h-5 text-violet-600" />
                        ノード編集
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
                            rows={3}
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
                                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addChecklistItem())}
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
                                    <div key={i} className="flex items-center justify-between text-xs bg-[var(--background)] rounded px-2 py-1 border border-[var(--border)]">
                                        <span>{item}</span>
                                        <button
                                            onClick={() => setChecklist(checklist.filter((_, j) => j !== i))}
                                            className="text-red-500 hover:text-red-600 p-1"
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
                        onClick={handleSave}
                        disabled={!label.trim()}
                        className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors flex items-center gap-1.5 ${label.trim()
                            ? 'bg-violet-500 text-white hover:bg-violet-600 shadow-md shadow-violet-500/20'
                            : 'bg-[var(--border)] text-[var(--muted)] cursor-not-allowed'
                            }`}
                    >
                        <Save className="w-4 h-4" />
                        保存する
                    </button>
                </div>
            </div>
        </div>
    );
}
