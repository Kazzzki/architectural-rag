'use client';

import React, { useEffect, useRef } from 'react';
import { Issue } from '@/lib/issue_types';

interface NodeContextMenuProps {
  x: number;
  y: number;
  issue: Issue;
  onClose: () => void;
  onStatusChange: (issue: Issue, status: string) => void;
  onPriorityChange: (issue: Issue, priority: string) => void;
  onDelete: (issue: Issue) => void;
  onDuplicate: (issue: Issue) => void;
  onStartEdge: (issueId: string) => void;
  onAIInvestigate: (issue: Issue) => void;
  onOpenMemo: (issue: Issue) => void;
}

const STATUS_OPTIONS = ['発生中', '対応中', '解決済み'] as const;
const PRIORITY_OPTIONS = ['critical', 'normal', 'minor'] as const;
const PRIORITY_LABELS: Record<string, string> = { critical: 'Critical', normal: 'Normal', minor: 'Minor' };

export default function NodeContextMenu({
  x, y, issue, onClose,
  onStatusChange, onPriorityChange, onDelete, onDuplicate,
  onStartEdge, onAIInvestigate, onOpenMemo,
}: NodeContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  // ビューポート境界チェック（フリップ/シフト）
  useEffect(() => {
    if (!menuRef.current) return;
    const rect = menuRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (rect.right > vw) menuRef.current.style.left = `${x - rect.width}px`;
    if (rect.bottom > vh) menuRef.current.style.top = `${y - rect.height}px`;
  }, [x, y]);

  // クリック外で閉じる
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  const menuItemClass = "w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 transition-colors flex items-center gap-2";
  const subMenuClass = "absolute left-full top-0 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[120px] z-[110]";

  return (
    <div
      ref={menuRef}
      className="fixed bg-white border border-gray-200 rounded-lg shadow-xl py-1 min-w-[180px] z-[100]"
      style={{ left: x, top: y }}
    >
      {/* ステータス変更 */}
      <div className="relative group">
        <button className={menuItemClass}>
          <span className="w-4 text-center">●</span>
          ステータス変更
          <span className="ml-auto text-gray-400 text-xs">▶</span>
        </button>
        <div className={`${subMenuClass} hidden group-hover:block`}>
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => { onStatusChange(issue, s); onClose(); }}
              className={`${menuItemClass} ${issue.status === s ? 'bg-blue-50 text-blue-700 font-medium' : ''}`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* 優先度変更 */}
      <div className="relative group">
        <button className={menuItemClass}>
          <span className="w-4 text-center">⬆</span>
          優先度変更
          <span className="ml-auto text-gray-400 text-xs">▶</span>
        </button>
        <div className={`${subMenuClass} hidden group-hover:block`}>
          {PRIORITY_OPTIONS.map((p) => (
            <button
              key={p}
              onClick={() => { onPriorityChange(issue, p); onClose(); }}
              className={`${menuItemClass} ${issue.priority === p ? 'bg-blue-50 text-blue-700 font-medium' : ''}`}
            >
              {PRIORITY_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      <div className="border-t border-gray-100 my-1" />

      <button onClick={() => { onStartEdge(issue.id); onClose(); }} className={menuItemClass}>
        <span className="w-4 text-center">↗</span>
        因果エッジを引く
      </button>

      <button onClick={() => { onOpenMemo(issue); onClose(); }} className={menuItemClass}>
        <span className="w-4 text-center">📝</span>
        メモを追加
      </button>

      <button onClick={() => { onAIInvestigate(issue); onClose(); }} className={menuItemClass}>
        <span className="w-4 text-center">🔍</span>
        AI調査
      </button>

      <div className="border-t border-gray-100 my-1" />

      <button onClick={() => { onDuplicate(issue); onClose(); }} className={menuItemClass}>
        <span className="w-4 text-center">📋</span>
        複製
      </button>

      <button
        onClick={() => {
          if (window.confirm(`「${issue.title}」を削除しますか？`)) {
            onDelete(issue);
          }
          onClose();
        }}
        className={`${menuItemClass} text-red-600 hover:bg-red-50`}
      >
        <span className="w-4 text-center">🗑</span>
        削除
      </button>
    </div>
  );
}
