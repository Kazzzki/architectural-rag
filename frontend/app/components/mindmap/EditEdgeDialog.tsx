'use client';

import { useState, useEffect } from 'react';
import { X, Save, AlertCircle } from 'lucide-react';

interface EditEdgeDialogProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: (type: 'hard' | 'soft', reason: string) => void;
    initialType?: 'hard' | 'soft';
    initialReason?: string;
    title?: string;
}

export default function EditEdgeDialog({
    isOpen,
    onClose,
    onSave,
    initialType = 'hard',
    initialReason = '',
    title = '依存関係の設定'
}: EditEdgeDialogProps) {
    const [type, setType] = useState<'hard' | 'soft'>(initialType);
    const [reason, setReason] = useState(initialReason);

    // Sync state when dialog opens or initial values change
    useEffect(() => {
        if (isOpen) {
            setType(initialType);
            setReason(initialReason);
        }
    }, [isOpen, initialType, initialReason]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
                <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                    <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                        <AlertCircle className="w-5 h-5 text-blue-500" />
                        {title}
                    </h3>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-slate-200 rounded-full transition-colors text-slate-400"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-6 space-y-6">
                    {/* Type Selection */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">依存の種類</label>
                        <div className="grid grid-cols-2 gap-3">
                            <button
                                type="button"
                                onClick={() => setType('hard')}
                                className={`flex flex-col items-center gap-2 p-3 rounded-xl border-2 transition-all ${type === 'hard'
                                        ? 'border-rose-500 bg-rose-50 text-rose-700'
                                        : 'border-slate-100 bg-slate-50 text-slate-400 hover:border-slate-200'
                                    }`}
                            >
                                <div className={`w-10 h-1 rounded-full ${type === 'hard' ? 'bg-rose-500' : 'bg-slate-300'}`} />
                                <span className="text-sm font-bold">必須依存 (強)</span>
                                <span className="text-[10px] opacity-70">実線の赤い線</span>
                            </button>
                            <button
                                type="button"
                                onClick={() => setType('soft')}
                                className={`flex flex-col items-center gap-2 p-3 rounded-xl border-2 transition-all ${type === 'soft'
                                        ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                                        : 'border-slate-100 bg-slate-50 text-slate-400 hover:border-slate-200'
                                    }`}
                            >
                                <div className={`w-10 h-1 border-t-2 border-dashed ${type === 'soft' ? 'border-indigo-500' : 'border-slate-300'}`} />
                                <span className="text-sm font-bold">参照依存 (弱)</span>
                                <span className="text-[10px] opacity-70">点線の青い線</span>
                            </button>
                        </div>
                    </div>

                    {/* Reason Input */}
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">依存の理由 (任意)</label>
                        <textarea
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            placeholder="なぜこのノードに依存するのか..."
                            className="w-full h-24 px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-sm resize-none transition-all placeholder:text-slate-300"
                        />
                    </div>
                </div>

                <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-bold text-slate-500 hover:text-slate-700 transition-colors"
                    >
                        キャンセル
                    </button>
                    <button
                        onClick={() => onSave(type, reason)}
                        className="flex items-center gap-2 px-6 py-2 bg-blue-600 text-white text-sm font-bold rounded-xl hover:bg-blue-700 shadow-lg shadow-blue-200 active:scale-95 transition-all"
                    >
                        <Save className="w-4 h-4" />
                        保存する
                    </button>
                </div>
            </div>
        </div>
    );
}
