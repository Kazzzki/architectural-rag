'use client';

/**
 * MobileTreeNode.tsx
 * 因果ツリーのモバイル用ノード1件分のコンポーネント。
 *
 * - タッチターゲットは Apple HIG 準拠の 44px 以上を確保
 * - ノード種別の色分け: 根本原因=赤系 / 中間原因=橙系 / 事象=青系
 * - incomingEdge が渡されると、ノード上部に因果コネクタ行を表示
 */

import React from 'react';
import { ChevronRight, ChevronDown, AlertCircle, Clock, CheckCircle2, ArrowDown } from 'lucide-react';
import { Issue, IssueEdge } from '@/lib/issue_types';

interface MobileTreeNodeProps {
  issue: Issue;
  /** ツリーの深さ（0始まり）。インデント量の計算に使用 */
  depth: number;
  hasChildren: boolean;
  isCollapsed: boolean;
  /** フィルタで非強調表示にするか */
  isDimmed: boolean;
  /** 自分に入ってくるエッジが存在する */
  hasIncoming: boolean;
  /** 自分から出ていくエッジが存在する */
  hasOutgoing: boolean;
  onClick: () => void;
  onToggleCollapse: () => void;
  /** 親→自分の因果エッジ（あれば上部にコネクタ表示） */
  incomingEdge?: IssueEdge;
  /** エッジコネクタをタップしたときのコールバック */
  onEdgeClick?: () => void;
}

const CATEGORY_BADGE: Record<string, string> = {
  '工程':   'bg-blue-100 text-blue-700',
  'コスト': 'bg-yellow-100 text-yellow-700',
  '品質':   'bg-green-100 text-green-700',
  '安全':   'bg-red-100 text-red-700',
};

function getNodeStyle(hasIncoming: boolean, hasOutgoing: boolean): string {
  if (!hasIncoming && hasOutgoing) return 'bg-red-50 border-red-200';
  if (hasIncoming && hasOutgoing)  return 'bg-orange-50 border-orange-200';
  return 'bg-blue-50 border-blue-200';
}

function StatusIcon({ status }: { status: Issue['status'] }) {
  if (status === '解決済み') return <CheckCircle2 size={14} className="text-green-500 flex-shrink-0" />;
  if (status === '対応中')   return <Clock        size={14} className="text-orange-400 flex-shrink-0" />;
  return <AlertCircle size={14} className="text-red-400 flex-shrink-0" />;
}

export default function MobileTreeNode({
  issue,
  depth,
  hasChildren,
  isCollapsed,
  isDimmed,
  hasIncoming,
  hasOutgoing,
  onClick,
  onToggleCollapse,
  incomingEdge,
  onEdgeClick,
}: MobileTreeNodeProps) {
  const indentPx = depth * 20;

  return (
    <>
      {/* ───── 親→自分の因果エッジコネクタ ───── */}
      {incomingEdge && (
        <button
          onClick={(e) => { e.stopPropagation(); onEdgeClick?.(); }}
          className="flex items-center gap-1.5 w-full py-0.5 hover:bg-gray-50 active:bg-gray-100 transition-colors"
          style={{ paddingLeft: `${indentPx + 52}px` }}
          aria-label="因果関係を表示"
        >
          <div className={`w-px h-3 flex-shrink-0 ${incomingEdge.confirmed ? 'bg-red-300' : 'bg-gray-300'}`} />
          <ArrowDown size={10} className={incomingEdge.confirmed ? 'text-red-400' : 'text-gray-400'} />
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
            incomingEdge.confirmed
              ? 'bg-red-100 text-red-600'
              : 'bg-gray-100 text-gray-500'
          }`}>
            {incomingEdge.confirmed ? '確定因果' : '仮設因果'}
          </span>
        </button>
      )}

      {/* ───── ノード行 ───── */}
      <div
        className={`flex items-stretch border-b border-gray-100 transition-opacity ${isDimmed ? 'opacity-30' : 'opacity-100'}`}
        style={{ paddingLeft: `${indentPx}px` }}
      >
        {/* 深さに応じた縦線 */}
        {depth > 0 && (
          <div className="w-px bg-gray-200 self-stretch mr-2 flex-shrink-0" />
        )}

        {/* 展開/折りたたみボタン */}
        <button
          onClick={onToggleCollapse}
          className="flex-shrink-0 flex items-center justify-center w-[44px] min-h-[44px] text-gray-400 active:bg-gray-100"
          aria-label={isCollapsed ? '子課題を展開' : '子課題を折りたたむ'}
        >
          {hasChildren ? (
            isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />
          ) : (
            <span className="w-1.5 h-1.5 rounded-full bg-gray-300 inline-block" />
          )}
        </button>

        {/* ノード本体 */}
        <button
          onClick={onClick}
          className={`flex-1 flex items-center gap-2 min-h-[44px] px-3 py-2 my-1 mr-2 text-left rounded-xl border active:brightness-95 transition-all ${getNodeStyle(hasIncoming, hasOutgoing)}`}
        >
          <StatusIcon status={issue.status} />

          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-800 truncate leading-tight">
              {issue.title}
            </div>
            {issue.assignee && (
              <div className="text-[10px] text-gray-400 truncate mt-0.5">{issue.assignee}</div>
            )}
          </div>

          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0 ${
            CATEGORY_BADGE[issue.category] ?? 'bg-gray-100 text-gray-600'
          }`}>
            {issue.category}
          </span>

          {issue.priority === 'critical' && (
            <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
          )}
        </button>
      </div>
    </>
  );
}
