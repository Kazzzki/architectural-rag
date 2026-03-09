'use client';

import React from 'react';
import { Loader2, CheckCircle2, AlertCircle, RefreshCw, FileEdit } from 'lucide-react';

interface Props {
    status: 'idle' | 'saving' | 'saved' | 'dirty' | 'error';
    lastSavedAt?: string | null;
    onRetry?: () => void;
}

export default function SaveStatusOverlay({ status, lastSavedAt, onRetry }: Props) {
    if (status === 'idle' && !lastSavedAt) return null;

    return (
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[100] animate-in fade-in slide-in-from-top-4 duration-300">
            <div className={`
                flex items-center gap-2 px-4 py-2 rounded-full shadow-lg border backdrop-blur-md
                ${status === 'saving' ? 'bg-amber-50/90 border-amber-200 text-amber-600' : ''}
                ${status === 'saved' ? 'bg-emerald-50/90 border-emerald-200 text-emerald-600' : ''}
                ${status === 'dirty' ? 'bg-slate-50/90 border-slate-200 text-slate-500' : ''}
                ${status === 'error' ? 'bg-rose-50/90 border-rose-200 text-rose-600' : ''}
                ${status === 'idle' && lastSavedAt ? 'bg-white/90 border-slate-100 text-slate-400 opacity-60' : ''}
            `}>
                {status === 'saving' && (
                    <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="text-xs font-bold">保存中...</span>
                    </>
                )}
                {status === 'saved' && (
                    <>
                        <CheckCircle2 className="w-4 h-4" />
                        <span className="text-xs font-bold">保存済み</span>
                    </>
                )}
                {status === 'dirty' && (
                    <>
                        <FileEdit className="w-4 h-4" />
                        <span className="text-xs font-bold">未保存の変更があります</span>
                    </>
                )}
                {status === 'error' && (
                    <>
                        <AlertCircle className="w-4 h-4" />
                        <span className="text-xs font-bold mr-1">保存に失敗しました</span>
                        {onRetry && (
                            <button
                                onClick={onRetry}
                                className="flex items-center gap-1 bg-rose-600 text-white px-2 py-0.5 rounded text-[10px] hover:bg-rose-700 transition-colors"
                            >
                                <RefreshCw className="w-3 h-3" />
                                再試行
                            </button>
                        )}
                    </>
                )}
                {status === 'idle' && lastSavedAt && (
                    <span className="text-[10px] font-medium">最終保存: {lastSavedAt}</span>
                )}
            </div>
        </div>
    );
}
