'use client';

import React, { memo, useState, useRef, useEffect, useCallback } from 'react';
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

export interface IssueNodeData {
  issue: Issue;
  hiddenChildCount?: number;
  hasChildren?: boolean;
  notesExpanded?: boolean;
  attachmentCount?: number;
  onClick?: (issue: Issue) => void;
  onCollapseToggle?: (issue: Issue) => void;
  onTitleChange?: (issueId: string, newTitle: string) => void;
  onToggleNotes?: (issueId: string) => void;
}

function IssueNode({ data, selected }: NodeProps<IssueNodeData>) {
  const { issue, hiddenChildCount = 0, hasChildren = false, notesExpanded = false, attachmentCount = 0, onClick, onCollapseToggle, onTitleChange, onToggleNotes } = data;
  const style = PRIORITY_STYLES[issue.priority] ?? PRIORITY_STYLES.normal;
  const statusColor = STATUS_COLOR[issue.status] ?? '#999';
  const showCollapseBtn = hasChildren || issue.is_collapsed === 1;

  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(issue.title);
  const inputRef = useRef<HTMLInputElement>(null);
  const tapTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setEditValue(issue.title);
  }, [issue.title]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commitEdit = useCallback(() => {
    setEditing(false);
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== issue.title) {
      onTitleChange?.(issue.id, trimmed);
    } else {
      setEditValue(issue.title);
    }
  }, [editValue, issue.id, issue.title, onTitleChange]);

  const handleTitleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    // ダブルタップ検出（300ms以内の2回タップ）
    if (tapTimerRef.current) {
      clearTimeout(tapTimerRef.current);
      tapTimerRef.current = null;
      setEditing(true);
    } else {
      tapTimerRef.current = setTimeout(() => {
        tapTimerRef.current = null;
        // シングルタップ → 通常のonClick
        onClick?.(issue);
      }, 300);
    }
  }, [onClick, issue]);

  return (
    <div
      onClick={(e) => {
        // 編集中はonClickを発火しない
        if (editing) { e.stopPropagation(); return; }
      }}
      style={{
        border: selected ? '2.5px solid #3b82f6' : style.border,
        backgroundColor: style.bg,
        borderRadius: 8,
        padding: '10px 14px',
        minWidth: 170,
        maxWidth: 220,
        cursor: 'pointer',
        position: 'relative',
        userSelect: 'none',
        boxShadow: selected ? '0 0 0 3px rgba(59,130,246,0.3)' : undefined,
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
        {editing ? (
          <input
            ref={inputRef}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitEdit();
              if (e.key === 'Escape') { setEditValue(issue.title); setEditing(false); }
            }}
            onClick={(e) => e.stopPropagation()}
            style={{
              fontSize: 14,
              fontWeight: 600,
              lineHeight: 1.3,
              width: '100%',
              border: '1px solid #4B9EF5',
              borderRadius: 4,
              padding: '1px 4px',
              outline: 'none',
              background: 'rgba(255,255,255,0.9)',
            }}
          />
        ) : (
          <span
            onClick={handleTitleClick}
            style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3, cursor: 'text' }}
          >
            {issue.title}
          </span>
        )}
      </div>

      {/* 担当者・期限 */}
      {(issue.assignee || issue.deadline) && (
        <div style={{ fontSize: 11, color: '#666', marginTop: 3, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {issue.assignee && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <span style={{ fontSize: 10 }}>👤</span>{issue.assignee}
            </span>
          )}
          {issue.deadline && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 2, color: new Date(issue.deadline) < new Date() ? '#DC2626' : '#666' }}>
              <span style={{ fontSize: 10 }}>📅</span>{issue.deadline}
            </span>
          )}
        </div>
      )}

      {/* カテゴリ + 添付 */}
      <div style={{ fontSize: 11, color: '#888', marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
        <span>{issue.category}</span>
        {attachmentCount > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 1, color: '#6B7280' }}>
            <span style={{ fontSize: 10 }}>📎</span>{attachmentCount}
          </span>
        )}
      </div>

      {/* メモプレビュー */}
      {issue.context_memo && (
        <div style={{
          fontSize: 10,
          color: '#666',
          marginTop: 3,
          padding: '2px 4px',
          background: 'rgba(0,0,0,0.04)',
          borderRadius: 3,
          lineHeight: 1.3,
          overflow: 'hidden',
          maxHeight: 28,
          whiteSpace: 'nowrap',
          textOverflow: 'ellipsis',
        }}>
          {issue.context_memo.slice(0, 40)}
        </div>
      )}

      {/* ノート展開ボタン */}
      {onToggleNotes && (
        <button
          onClick={(e) => { e.stopPropagation(); onToggleNotes(issue.id); }}
          title={notesExpanded ? 'ノートを閉じる' : 'ノートを展開'}
          style={{
            position: 'absolute',
            top: 4,
            left: 6,
            fontSize: 12,
            background: notesExpanded ? '#FDE68A' : 'rgba(0,0,0,0.05)',
            border: 'none',
            borderRadius: 4,
            padding: '2px 5px',
            cursor: 'pointer',
            lineHeight: 1.2,
          }}
        >
          📝
        </button>
      )}

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
            borderRadius: 6,
            padding: '4px 10px',
            cursor: 'pointer',
            lineHeight: 1.5,
            minHeight: 28,
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
