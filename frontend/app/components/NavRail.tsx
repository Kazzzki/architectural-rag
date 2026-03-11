import React from 'react';
import { 
    MessageSquare, 
    Library as LibraryIcon,
    GitBranch,
    Layers,
    Settings,
    Building2 
} from 'lucide-react';

export type NavItemId = 'chat' | 'library' | 'mindmap' | 'layers' | 'settings';

export interface NavRailProps {
    activeItem: NavItemId | null;
    onSelect: (id: NavItemId | null) => void;
}

export default function NavRail({ activeItem, onSelect }: NavRailProps) {
    const navItems = [
        { id: 'chat' as NavItemId, icon: MessageSquare, title: 'チャット履歴' },
        { id: 'library' as NavItemId, icon: LibraryIcon, title: 'ナレッジライブラリ' },
        { id: 'mindmap' as NavItemId, icon: GitBranch, title: 'マインドマップ' },
        { id: 'layers' as NavItemId, icon: Layers, title: 'AI Layers' },
        { id: 'settings' as NavItemId, icon: Settings, title: '設定' },
    ];

    return (
        <div className="w-12 h-screen border-r border-[var(--border)] bg-gray-50 flex-shrink-0 flex flex-col items-center py-4 z-20">
            {/* Logo */}
            <div className="mb-6 select-none flex-shrink-0">
                <Building2 className="w-6 h-6 text-primary-500" />
            </div>

            {/* Nav Items */}
            <div className="flex-1 flex flex-col gap-3 w-full items-center">
                {navItems.map(item => {
                    const Icon = item.icon;
                    const isActive = activeItem === item.id;
                    return (
                        <button
                            key={item.id}
                            onClick={() => onSelect(isActive ? null : item.id)}
                            title={item.title}
                            className={`relative w-10 h-10 rounded-xl flex items-center justify-center group transition-colors flex-shrink-0
                                ${isActive ? 'text-primary-600 bg-primary-100 shadow-sm' : 'text-gray-500 hover:bg-gray-200 hover:text-gray-800'}
                            `}
                        >
                            {isActive && (
                                <div className="absolute left-[-4px] top-1/2 -translate-y-1/2 h-5 w-1 bg-primary-600 rounded-r-full" />
                            )}
                            <Icon className="w-5 h-5 transition-transform group-active:scale-95" strokeWidth={isActive ? 2.5 : 2} />
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
