'use client';

import React, { useState } from 'react';
import { EdgeProps, getBezierPath, EdgeLabelRenderer, BaseEdge } from 'reactflow';
import EdgeLabelEditor from './EdgeLabelEditor';
import type { EdgeRelationType } from '@/lib/issue_types';

interface DeletableEdgeData {
  onDeleteEdge?: (id: string) => void;
  onEdgeUpdated?: () => void;
  label?: string | null;
  relationType?: EdgeRelationType | null;
}

export default function DeletableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  data,
}: EdgeProps<DeletableEdgeData>) {
  const [hovered, setHovered] = useState(false);
  const [showEditor, setShowEditor] = useState(false);

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      {/* 透明な太めのパス（ホバー検出用） */}
      <path
        d={edgePath}
        fill="none"
        strokeWidth={16}
        stroke="transparent"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => { if (!showEditor) setHovered(false); }}
        onDoubleClick={(e) => { e.stopPropagation(); setShowEditor(true); setHovered(true); }}
        style={{ cursor: 'pointer' }}
      />
      <BaseEdge
        id={id}
        path={edgePath}
        style={style}
        markerEnd={markerEnd}
      />
      {hovered && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => { if (!showEditor) setHovered(false); }}
            className="nodrag nopan"
          >
            <div style={{ display: 'flex', gap: 4 }}>
              {/* 編集ボタン */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setShowEditor(true);
                }}
                style={{
                  width: 20, height: 20, borderRadius: '50%',
                  background: '#3b82f6', color: '#fff', border: 'none',
                  cursor: 'pointer', fontSize: 11, lineHeight: 1,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                }}
                title="エッジを編集"
              >
                ✎
              </button>
              {/* 削除ボタン */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  data?.onDeleteEdge?.(id);
                }}
                style={{
                  width: 20, height: 20, borderRadius: '50%',
                  background: '#ef4444', color: '#fff', border: 'none',
                  cursor: 'pointer', fontSize: 13, lineHeight: 1,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                }}
                title="エッジを削除"
              >
                ×
              </button>
            </div>
          </div>
        </EdgeLabelRenderer>
      )}
      {/* エッジラベル編集パネル */}
      {showEditor && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, 10px) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan"
          >
            <EdgeLabelEditor
              edgeId={id}
              currentLabel={data?.label ?? null}
              currentType={data?.relationType ?? null}
              x={0}
              y={0}
              onClose={() => { setShowEditor(false); setHovered(false); }}
              onUpdated={() => { setShowEditor(false); setHovered(false); data?.onEdgeUpdated?.(); }}
            />
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
