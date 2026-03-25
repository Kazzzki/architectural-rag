'use client';

import React, { memo, useState, useCallback, useRef, useEffect } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Issue } from '@/lib/issue_types';
import { authFetch } from '@/lib/api';
import { StickyNote, MoreHorizontal } from 'lucide-react';
import MemoPopover from './MemoPopover';

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
  isSelected?: boolean;
  isEditing?: boolean;
  onClick?: (issue: Issue) => void;
  onCollapseToggle?: (issue: Issue) => void;
  onTitleUpdated?: (updated: Issue) => void;
  onContextMenu?: (issue: Issue) => void;
  onMemoUpdated?: (updated: Issue) => void;
}

function IssueNode({ data }: NodeProps<IssueNodeData>) {
  const { issue, hiddenChildCount = 0, hasChildren = false, isSelected = false, onClick, onCollapseToggle, onTitleUpdated, onContextMenu, onMemoUpdated } = data;
  const style = PRIORITY_STYLES[issue.priority] ?? PRIORITY_STYLES.normal;
  const statusColor = STATUS_COLOR[issue.status] ?? '#999';
  const showCollapseBtn = hasChildren || issue.is_collapsed === 1;

  // インライン編集状態
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(issue.title);
  const inputRef = useRef<HTMLInputElement>(null);

  // メモポップオーバー
  const [showMemo, setShowMemo] = useState(false);

  const hasMemo = !!(issue.context_memo && issue.context_memo.trim());

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setEditTitle(issue.title);
    setEditing(true);
  }, [issue.title]);

  const handleSaveTitle = useCallback(async () => {
    setEditing(false);
    const trimmed = editTitle.trim();
    if (!trimmed || trimmed === issue.title) return;
    try {
      const res = await authFetch(`/api/issues/${issue.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: trimmed }),
      });
      if (res.ok) {
        const updated: Issue = await res.json();
        onTitleUpdated?.(updated);
      }
    } catch {}
  }, [editTitle, issue.id, issue.title, onTitleUpdated]);

  return (
    <div
      onClick={() => !editing && onClick?.(issue)}
      onDoubleClick={handleDoubleClick}
      style={{
        border: isSelected ? '2.5px solid #3B82F6' : style.border,
        backgroundColor: style.bg,
        borderRadius: 8,
        padding: '10px 14px',
        minWidth: 170,
        maxWidth: 220,
        cursor: 'pointer',
        position: 'relative',
        userSelect: 'none',
        boxShadow: isSelected ? '0 0 0 3px rgba(59,130,246,0.2)' : undefined,
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#888' }} />

      {/* ステータス円 (右上) */}
      <div
        style={{
          position: 'absolute', top: 6, right: 6,
          width: 10, height: 10, borderRadius: '50%',
          backgroundColor: statusColor,
          border: '1px solid rgba(0,0,0,0.2)',
        }}
      />

      {/* アイコンゾーン（右上） */}
      <div style={{ position: 'absolute', top: 5, right: 22, display: 'flex', gap: 2 }}>
        {/* メモアイコン */}
        {hasMemo && (
          <button
            onClick={(e) => { e.stopPropagation(); setShowMemo(!showMemo); }}
            className="nodrag nopan"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 1 }}
            title="メモを表示"
          >
            <StickyNote size={12} color="#D97706" />
          </button>
        )}
        {/* 「...」ボタン（コンテキストメニュー代替入口） */}
        <button
          onClick={(e) => { e.stopPropagation(); onContextMenu?.(issue); }}
          className="nodrag nopan"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 1, opacity: 0.5 }}
          title="メニュー"
        >
          <MoreHorizontal size={12} />
        </button>
      </div>

      {/* タイトル行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, paddingRight: 40 }}>
        {style.badge && <span style={{ fontSize: 11 }}>{style.badge}</span>}
        {editing ? (
          <input
            ref={inputRef}
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onBlur={handleSaveTitle}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSaveTitle();
              if (e.key === 'Escape') { setEditing(false); setEditTitle(issue.title); }
            }}
            onClick={(e) => e.stopPropagation()}
            className="nodrag nopan"
            style={{
              fontSize: 14, fontWeight: 600, lineHeight: 1.3,
              border: '1px solid #3B82F6', borderRadius: 4,
              padding: '1px 4px', width: '100%', background: 'white',
              outline: 'none',
            }}
          />
        ) : (
          <span style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>
            {issue.title}
          </span>
        )}
      </div>

      {/* カテゴリ・重要度 */}
      <div style={{ fontSize: 12, color: '#555', marginTop: 4 }}>
        {issue.category} / {issue.status}
      </div>

      {/* 折りたたみバッジ */}
      {hiddenChildCount > 0 && (
        <div style={{
          position: 'absolute', bottom: 4, right: 6,
          fontSize: 10, background: '#666', color: '#fff',
          borderRadius: 10, padding: '1px 5px',
        }}>
          +{hiddenChildCount}
        </div>
      )}

      {/* 折りたたみトグルボタン */}
      {showCollapseBtn && (
        <button
          onClick={(e) => { e.stopPropagation(); onCollapseToggle?.(issue); }}
          title={issue.is_collapsed === 1 ? '子ノードを展開' : '子ノードを折りたたむ'}
          style={{
            position: 'absolute', bottom: 4, left: 6,
            fontSize: 10,
            background: issue.is_collapsed === 1 ? '#4B9EF5' : '#888',
            color: '#fff', border: 'none', borderRadius: 4,
            padding: '1px 5px', cursor: 'pointer', lineHeight: 1.5,
          }}
        >
          {issue.is_collapsed === 1 ? '▶ 展開' : '▼ 折りたたむ'}
        </button>
      )}

      {/* メモポップオーバー */}
      {showMemo && (
        <MemoPopover
          issue={issue}
          onClose={() => setShowMemo(false)}
          onUpdated={(updated) => { onMemoUpdated?.(updated); setShowMemo(false); }}
        />
      )}

      <Handle type="source" position={Position.Right} style={{ background: '#888' }} />
    </div>
  );
}

export default memo(IssueNode);
