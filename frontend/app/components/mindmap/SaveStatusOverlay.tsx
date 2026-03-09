'use client';

import React from 'react';
import { Loader2, CheckCircle2 } from 'lucide-react';

interface Props {
    status: 'idle' | 'saving' | 'saved';
}

export default function SaveStatusOverlay({ status }: Props) {
    if (status === 'idle') return null;

    return (
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[100] animate-in fade-in slide-in-from-top-4 duration-300">
            <div className={`
                flex items-center gap-2 px-4 py-2 rounded-full shadow-lg border
                ${status === 'saving'
                    ? 'bg-amber-50 border-amber-200 text-amber-600'
                    : 'bg-emerald-50 border-emerald-200 text-emerald-600'
                }
            `}>
                {status === 'saving' ? (
                    <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="text-xs font-bold">変更を保存中...</span>
                    </>
                ) : (
                    <>
                        <CheckCircle2 className="w-4 h-4" />
                        <span className="text-xs font-bold">保存しました</span>
                    </>
                )}
            </div>
        </div>
    );
}
