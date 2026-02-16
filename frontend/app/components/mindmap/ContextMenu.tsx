'use client';

import { useEffect, useRef } from 'react';
import { Plus, Edit2, Trash2, ArrowRight, CornerDownRight, Minimize2, Maximize2 } from 'lucide-react';

interface MenuOption {
    label: string;
    icon?: React.ReactNode;
    action: () => void;
    shortcut?: string;
    danger?: boolean;
    disabled?: boolean;
}

interface Props {
    x: number;
    y: number;
    options: MenuOption[];
    onClose: () => void;
}

export default function ContextMenu({ x, y, options, onClose }: Props) {
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                onClose();
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [onClose]);

    // Prevent menu from going off-screen
    const style: React.CSSProperties = {
        top: y,
        left: x,
    };

    // Simple screen boundary check could be added here if needed, 
    // but for now we rely on the canvas size being large enough.

    return (
        <div
            ref={menuRef}
            className="fixed z-50 bg-white rounded-lg shadow-xl border border-slate-200 py-1 min-w-[200px] animate-in fade-in zoom-in-95 duration-100"
            style={style}
            onContextMenu={(e) => e.preventDefault()}
        >
            {options.map((option, i) => (
                <button
                    key={i}
                    onClick={() => {
                        if (!option.disabled) {
                            option.action();
                            onClose();
                        }
                    }}
                    disabled={option.disabled}
                    className={`
                        w-full text-left px-4 py-2 text-xs font-medium flex items-center justify-between
                        ${option.danger
                            ? 'text-red-600 hover:bg-red-50'
                            : 'text-slate-700 hover:bg-slate-50'
                        }
                        ${option.disabled ? 'opacity-50 cursor-not-allowed' : ''}
                    `}
                >
                    <div className="flex items-center gap-2">
                        {option.icon && <span className="w-4 h-4 text-slate-400">{option.icon}</span>}
                        <span>{option.label}</span>
                    </div>
                    {option.shortcut && <span className="text-slate-400 text-[10px] ml-4">{option.shortcut}</span>}
                </button>
            ))}
        </div>
    );
}
