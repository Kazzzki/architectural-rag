'use client';

import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Issue } from '@/lib/issue_types';

const PRIORITY_STYLES: Record<string, { border: string; bg: string; badge?: string }> = {
  critical: { border: '2.5px solid #A32D2D', bg: '#F7C1C1', badge: '🔴' },
  normal:   { border: '1.5px solid #185FA5', bg: '#B5D4F4' },
  minor:    { border: '1px solid #B4B2A9',   bg: '#F1EFE8' },
};

const STATUS_COLOR: Record<string, string> = {
  '発生中': '#E63946',
  '対応中': '#F4A261',
  '解決済み': '#52B788',
};

interface IssueNodeData {
  issue: Issue;
  hiddenChildCount?: number;
  onClick?: (issue: Issue) => void;
}

function IssueNode({ data }: NodeProps<IssueNodeData>) {
  const { issue, hiddenChildCount = 0, onClick } = data;
  const style = PRIORITY_STYLES[issue.priority] ?? PRIORITY_STYLES.normal;
  const statusColor = STATUS_COLOR[issue.status] ?? '#999';

  return (
    <div
      onClick={() => onClick?.(issue)}
      style={{
        border: style.border,
        backgroundColor: style.bg,
        borderRadius: 10,
        padding: '10px 14px',
        minWidth: 160,
        maxWidth: 220,
        minHeight: 44, // モバイルのタッチターゲット最小高さ
        cursor: 'pointer',
        position: 'relative',
        userSelect: 'none',
        boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#888', width: 8, height: 8 }} />

      {/* ステータス円 (右上) */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          right: 8,
          width: 10,
          height: 10,
          borderRadius: '50%',
          backgroundColor: statusColor,
          border: '1.5px solid rgba(255,255,255,0.8)',
          boxShadow: '0 0 0 1px rgba(0,0,0,0.12)',
        }}
      />

      {/* タイトル行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, paddingRight: 18 }}>
        {style.badge && <span style={{ fontSize: 11, lineHeight: 1 }}>{style.badge}</span>}
        <span style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.35, color: '#1a1a1a' }}>
          {issue.title}
        </span>
      </div>

      {/* カテゴリ・ステータス */}
      <div style={{ fontSize: 11, color: '#666', marginTop: 4, display: 'flex', gap: 4, alignItems: 'center' }}>
        <span>{issue.category}</span>
        <span style={{ color: '#ccc' }}>·</span>
        <span>{issue.status}</span>
      </div>

      {/* 折りたたみバッジ */}
      {hiddenChildCount > 0 && (
        <div
          style={{
            position: 'absolute',
            bottom: 5,
            right: 7,
            fontSize: 10,
            background: '#555',
            color: '#fff',
            borderRadius: 10,
            padding: '1px 6px',
            fontWeight: 600,
          }}
        >
          +{hiddenChildCount}
        </div>
      )}

      <Handle type="source" position={Position.Right} style={{ background: '#888', width: 8, height: 8 }} />
    </div>
  );
}

export default memo(IssueNode);
