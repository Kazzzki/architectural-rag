'use client';

import React, { useState } from 'react';
import { EdgeProps, getBezierPath, EdgeLabelRenderer, BaseEdge } from 'reactflow';

interface DeletableEdgeData {
  onDeleteEdge?: (id: string) => void;
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
        onMouseLeave={() => setHovered(false)}
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
            onMouseLeave={() => setHovered(false)}
            className="nodrag nopan"
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                data?.onDeleteEdge?.(id);
              }}
              style={{
                width: 20,
                height: 20,
                borderRadius: '50%',
                background: '#ef4444',
                color: '#fff',
                border: 'none',
                cursor: 'pointer',
                fontSize: 13,
                lineHeight: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
              }}
              title="エッジを削除"
            >
              ×
            </button>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
