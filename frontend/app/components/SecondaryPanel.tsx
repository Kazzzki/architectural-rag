import React from 'react';
import { ChevronLeft } from 'lucide-react';
import { NavItemId } from './NavRail';

export interface SecondaryPanelProps {
    activeItem: NavItemId | null;
    isOpen: boolean;
    onClose: () => void;
    children?: React.ReactNode;
}

export default function SecondaryPanel({ activeItem, isOpen, onClose, children }: SecondaryPanelProps) {
    const getTitle = () => {
        switch (activeItem) {
            case 'chat': return 'チャット履歴';
            case 'library': return 'ナレッジライブラリ';
            case 'mindmap': return 'マインドマップ';
            case 'layers': return 'AI Layers';
            case 'settings': return '設定';
            default: return '';
        }
    };

    return (
        <div 
            className={`flex-shrink-0 bg-white border-r border-[var(--border)] transition-all duration-200 ease-in-out h-full flex flex-col overflow-hidden z-10 shadow-sm
                ${isOpen ? 'w-72' : 'w-0'}
            `}
        >
            {/* Header */}
            <div className="h-14 flex items-center justify-between px-4 border-b border-[var(--border)] flex-shrink-0 min-w-[288px]">
                <h2 className="font-bold text-sm tracking-tight text-[var(--foreground)]">{getTitle()}</h2>
                <button 
                    onClick={onClose}
                    className="p-1.5 rounded-lg text-[var(--muted)] hover:bg-[var(--card-hover)] hover:text-[var(--foreground)] transition-colors"
                >
                    <ChevronLeft className="w-4 h-4" />
                </button>
            </div>

            {/* Content Container */}
            <div className="flex-1 overflow-y-auto custom-scrollbar min-w-[288px] flex flex-col">
                {children}
            </div>
        </div>
    );
}
