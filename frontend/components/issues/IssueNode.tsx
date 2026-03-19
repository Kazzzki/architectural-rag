'use client';

import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Issue } from '@/lib/issue_types';

const PRIORITY_STYLES: Record<string, { border: string; bg: string; badge?: string }> = {
  critical: { border: '2.5px solid #A32D2D', bg: '#F7C1C1', badge: '🔴' },
  normal:   { border: '1px solid #185FA5',   bg: '#B5D4F4' },
  minor:    { border: '0.5px solid #B4B2A9', bg: '#F1EFE8' },
};

const STATUS_COLOR: Record<string, string> = {
  '発生中': '#E63946',
  '対応中': '#F4A261',
  '解決済み': '#52B788',
};

interface IssueNodeData {
  issue: Issue;
  hiddenChildCount?: number;
  hasChildren?: boolean;
  onClick?: (issue: Issue) => void;
  onCollapseToggle?: (issue: Issue) => void;
}

function IssueNode({ data }: NodeProps<IssueNodeData>) {
  const { issue, hiddenChildCount = 0, hasChildren = false, onClick, onCollapseToggle } = data;
  const style = PRIORITY_STYLES[issue.priority] ?? PRIORITY_STYLES.normal;
  const statusColor = STATUS_COLOR[issue.status] ?? '#999';
  const showCollapseBtn = hasChildren || issue.is_collapsed === 1;

  return (
    <div
      onClick={() => onClick?.(issue)}
      style={{
        border: style.border,
        backgroundColor: style.bg,
        borderRadius: 8,
        padding: '10px 14px',
        minWidth: 170,
        maxWidth: 220,
        cursor: 'pointer',
        position: 'relative',
        userSelect: 'none',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#888' }} />

      {/* ステータス円 (右上) */}
      <div
        style={{
          position: 'absolute',
          top: 6,
          right: 6,
          width: 10,
          height: 10,
          borderRadius: '50%',
          backgroundColor: statusColor,
          border: '1px solid rgba(0,0,0,0.2)',
        }}
      />

      {/* タイトル行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, paddingRight: 16 }}>
        {style.badge && <span style={{ fontSize: 11 }}>{style.badge}</span>}
        <span style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>
          {issue.title}
        </span>
      </div>

      {/* カテゴリ・重要度 */}
      <div style={{ fontSize: 12, color: '#555', marginTop: 4 }}>
        {issue.category} / {issue.status}
      </div>

      {/* 折りたたみバッジ */}
      {hiddenChildCount > 0 && (
        <div
          style={{
            position: 'absolute',
            bottom: 4,
            right: 6,
            fontSize: 10,
            background: '#666',
            color: '#fff',
            borderRadius: 10,
            padding: '1px 5px',
          }}
        >
          +{hiddenChildCount}
        </div>
      )}

      {/* 折りたたみトグルボタン */}
      {showCollapseBtn && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onCollapseToggle?.(issue);
          }}
          title={issue.is_collapsed === 1 ? '子ノードを展開' : '子ノードを折りたたむ'}
          style={{
            position: 'absolute',
            bottom: 4,
            left: 6,
            fontSize: 10,
            background: issue.is_collapsed === 1 ? '#4B9EF5' : '#888',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            padding: '1px 5px',
            cursor: 'pointer',
            lineHeight: 1.5,
          }}
        >
          {issue.is_collapsed === 1 ? '▶ 展開' : '▼ 折りたたむ'}
        </button>
      )}

      <Handle type="source" position={Position.Right} style={{ background: '#888' }} />
    </div>
  );
}

export default memo(IssueNode);
