'use client';

import React, { useState } from 'react';
import { FileText, ExternalLink } from 'lucide-react';
import { SourceFile } from '../../lib/api';

const PAGE_CHIP_LIMIT = 5;

// doc_type バッジ
const DOC_TYPE_BADGE: Record<string, { label: string; cls: string }> = {
    drawing: { label: '📐 図面', cls: 'bg-blue-500/15 text-blue-300 border-blue-500/30' },
    law: { label: '⚖️ 法規', cls: 'bg-red-500/15 text-red-300 border-red-500/30' },
    spec: { label: '📋 仕様書', cls: 'bg-green-500/15 text-green-300 border-green-500/30' },
    catalog: { label: '📦 カタログ', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
};

export default function SourceCard({
    src,
    onPageClick,
}: {
    src: SourceFile;
    onPageClick: (url: string, page: number) => void;
}) {
    const [expanded, setExpanded] = useState(false);
    const badge = DOC_TYPE_BADGE[src.doc_type];
    
    // hit_count に基づく関連度表示
    const relevanceDots = src.hit_count >= 3 ? '●●●' : src.hit_count === 2 ? '●●○' : '●○○';

    const visiblePages = expanded ? src.pages : src.pages.slice(0, PAGE_CHIP_LIMIT);
    const hiddenCount = src.pages.length - PAGE_CHIP_LIMIT;

    // lib/pdf.ts or similar is missing, so we'll construct the URL here or pass it down
    // For now, let's assume src.source_pdf is the path or ID
    const resolvedUrl = src.source_pdf ? `/api/pdf/${src.source_pdf}` : null;

    return (
        <div className="flex flex-col gap-1.5 bg-white border border-gray-200 px-3 py-2 rounded-lg text-xs min-w-[180px] max-w-[260px] relative shadow-sm hover:border-primary-300 transition-colors">
            <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-bold text-gray-500 bg-gray-50 border border-gray-100 px-1.5 py-0.5 rounded">
                    {src.source_id}
                </span>
                {badge && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.cls}`}>
                        {badge.label}
                    </span>
                )}
                <span className="ml-auto text-[10px] text-gray-400" title={`ヒット数: ${src.hit_count}`}>
                    {relevanceDots}
                </span>
            </div>

            <div className="flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-primary-500 shrink-0" />
                <span className="font-medium text-gray-900 truncate">
                    {src.original_filename || src.source_pdf_name || src.filename}
                </span>
            </div>

            {src.pages.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-0.5">
                    {visiblePages.map((p: number) => (
                        <button
                            key={p}
                            onClick={() => resolvedUrl && onPageClick(resolvedUrl, p)}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100 hover:bg-blue-100 transition-colors cursor-pointer"
                        >
                            p.{p}
                        </button>
                    ))}
                    {!expanded && hiddenCount > 0 && (
                        <button
                            onClick={() => setExpanded(true)}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-gray-50 text-gray-500 border border-gray-100 hover:bg-gray-100 transition-colors"
                        >
                            +{hiddenCount}
                        </button>
                    )}
                </div>
            )}

            {src.pages.length === 0 && resolvedUrl && (
                <button
                    onClick={() => onPageClick(resolvedUrl, 1)}
                    className="text-[10px] text-blue-600 hover:text-blue-700 flex items-center gap-1 underline"
                >
                    <ExternalLink className="w-2.5 h-2.5" />
                    PDF表示
                </button>
            )}
        </div>
    );
}
