import React, { useEffect } from 'react';
import { X, Command, ArrowUp } from 'lucide-react';

interface KeyboardShortcutsModalProps {
    isOpen: boolean;
    onClose: () => void;
}

const KeyboardShortcutsModal: React.FC<KeyboardShortcutsModalProps> = ({ isOpen, onClose }) => {
    // Esc is handled globally, but we can also handle it here if focused
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                onClose();
            }
        };
        if (isOpen) {
            window.addEventListener('keydown', handleKeyDown);
        }
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const shortcutCategories = [
        {
            title: 'ナビゲーション & 表示',
            shortcuts: [
                { keys: ['? / H'], desc: 'このヘルプを表示' },
                { keys: ['Cmd', 'B'], desc: 'サイドバーの開閉' },
                { keys: ['Cmd', 'K / F'], desc: 'マップ内検索へフォーカス' },
                { keys: ['0'], desc: 'ズームをリセット (Fit View)' },
                { keys: ['Shift', 'F'], desc: 'ズームをリセット (Fit View - 代替)' },
                { keys: ['Space + ドラッグ'], desc: 'マップのパン移動' },
            ],
        },
        {
            title: 'ノード操作',
            shortcuts: [
                { keys: ['N'], desc: 'ルートノード追加' },
                { keys: ['Tab'], desc: '選択中ノードの子を追加' },
                { keys: ['Enter'], desc: '兄弟ノードを追加 / 次の検索結果へ移動' },
                { keys: ['Shift', 'Enter'], desc: '前の検索結果へ移動' },
                { keys: ['F / F2'], desc: 'ノードを編集' },
                { keys: ['Del / Backspace'], desc: '選択したノード/エッジを削除' },
            ],
        },
        {
            title: '選択 & 取り消し',
            shortcuts: [
                { keys: ['Cmd', 'A'], desc: '全ノード選択' },
                { keys: ['Esc'], desc: '選択・ダイアログ・検索をクリア' },
                { keys: ['Cmd', 'Z'], desc: '変更を取り消す (Undo)' },
                { keys: ['Cmd', 'S'], desc: '保存状態を表示 (Auto-saved)' },
            ],
        },
    ];

    const renderKey = (key: string, idx: number) => {
        if (key === 'Cmd') return <kbd key={idx} className="px-2 py-1 bg-gray-100 border border-gray-300 rounded text-xs text-gray-700 shadow-sm flex items-center justify-center"><Command className="w-3 h-3" /></kbd>;
        if (key === 'Shift') return <kbd key={idx} className="px-2 py-1 bg-gray-100 border border-gray-300 rounded text-xs text-gray-700 shadow-sm flex items-center justify-center"><ArrowUp className="w-3 h-3" /></kbd>;
        return <kbd key={idx} className="px-2 py-1 min-w-[24px] bg-gray-100 border border-gray-300 rounded text-xs text-gray-700 shadow-sm flex justify-center items-center">{key}</kbd>;
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
                    <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                        <Command className="w-5 h-5 text-violet-500" />
                        キーボードショートカット
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>
                
                <div className="flex-1 overflow-y-auto p-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {shortcutCategories.map((cat, i) => (
                            <div key={i} className={i === 2 ? 'md:col-span-2 md:w-1/2 md:pr-4' : ''}>
                                <h3 className="text-sm font-semibold text-violet-600 mb-3 ml-1 uppercase tracking-wider">{cat.title}</h3>
                                <div className="space-y-2">
                                    {cat.shortcuts.map((shortcut, j) => (
                                        <div key={j} className="flex justify-between items-center bg-white p-2 rounded-lg border border-gray-100 hover:border-violet-100 transition-colors">
                                            <span className="text-sm text-gray-600">{shortcut.desc}</span>
                                            <div className="flex items-center gap-1.5">
                                                {shortcut.keys.map((k, kIdx) => renderKey(k, kIdx))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 text-center">
                    <p className="text-xs text-gray-500 font-medium">
                        ヒント: <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded mx-1">?</kbd> または <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded mx-1">H</kbd> でいつでもこの画面を開けます。
                    </p>
                </div>
            </div>
        </div>
    );
};

export default KeyboardShortcutsModal;
