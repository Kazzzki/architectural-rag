'use client';

import React from 'react';
import { ZoomIn, ZoomOut, Maximize, Target, LayoutDashboard, Map as MapIcon } from 'lucide-react';
import { useReactFlow } from 'reactflow';

interface Props {
    onToggleMiniMap: () => void;
    showMiniMap: boolean;
    selectedNodeId: string | null;
}

export default function ViewportControls({ onToggleMiniMap, showMiniMap, selectedNodeId }: Props) {
    const { zoomIn, zoomOut, fitView, setViewport, getZoom, setCenter, getNodes } = useReactFlow();

    const handleZoomTo100 = () => {
        setViewport({ x: 0, y: 0, zoom: 1 }, { duration: 400 });
    };

    const handleFocusSelected = () => {
        if (!selectedNodeId) return;
        const node = getNodes().find((n) => n.id === selectedNodeId);
        if (node) {
            setCenter(node.position.x, node.position.y, { zoom: 1.1, duration: 400 });
        }
    };

    const currentZoom = Math.round((getZoom() || 1) * 100);

    return (
        <div className="absolute bottom-4 right-4 z-10 flex flex-col gap-2">
            {/* Zoom Controls */}
            <div className="flex flex-col bg-white/90 backdrop-blur-md border border-[var(--border)] rounded-xl shadow-xl overflow-hidden">
                <button
                    onClick={() => zoomIn({ duration: 300 })}
                    className="p-2 hover:bg-slate-50 text-slate-600 transition-colors border-b border-slate-100"
                    title="ズームイン"
                >
                    <ZoomIn className="w-4 h-4" />
                </button>
                <div className="py-1 text-[10px] font-bold text-slate-400 text-center bg-slate-50/50">
                    {currentZoom}%
                </div>
                <button
                    onClick={() => zoomOut({ duration: 300 })}
                    className="p-2 hover:bg-slate-50 text-slate-600 transition-colors border-t border-slate-100"
                    title="ズームアウト"
                >
                    <ZoomOut className="w-4 h-4" />
                </button>
            </div>

            {/* Viewport Actions */}
            <div className="flex flex-col bg-white/90 backdrop-blur-md border border-[var(--border)] rounded-xl shadow-xl overflow-hidden">
                <button
                    onClick={handleZoomTo100}
                    className="p-2 hover:bg-slate-50 text-slate-600 transition-colors border-b border-slate-100 font-bold text-[10px]"
                    title="100%にリセット"
                >
                    100%
                </button>
                <button
                    onClick={() => fitView({ duration: 400, padding: 0.2 })}
                    className="p-2 hover:bg-slate-50 text-slate-600 transition-colors border-b border-slate-100"
                    title="全体表示"
                >
                    <Maximize className="w-4 h-4" />
                </button>
                <button
                    onClick={handleFocusSelected}
                    disabled={!selectedNodeId}
                    className={`p-2 transition-colors border-b border-slate-100 ${selectedNodeId ? 'hover:bg-slate-50 text-slate-600' : 'text-slate-300 cursor-not-allowed'
                        }`}
                    title="選択ノードへ移動"
                >
                    <Target className="w-4 h-4" />
                </button>
                <button
                    onClick={onToggleMiniMap}
                    className={`p-2 transition-colors ${showMiniMap ? 'bg-violet-50 text-violet-600' : 'hover:bg-slate-50 text-slate-600'
                        }`}
                    title="ミニマップ表示/非表示"
                >
                    <MapIcon className="w-4 h-4" />
                </button>
            </div>
        </div>
    );
}
