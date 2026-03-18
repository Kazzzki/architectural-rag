'use client';

/**
 * MobileTreeNode.tsx
 * 因果ツリーのモバイル用ノード1件分のコンポーネント。
 *
 * ライブラリ選定メモ:
 * - 追加依存なし（Tailwind CSS + lucide-react のみ）
 * - タッチターゲットは Apple HIG 準拠の 44px 以上を確保
 * - ノード種別の色分け: 根本原因=赤系 / 中間原因=橙系 / 事象=青系
 */

import React from 'react';
import { ChevronRight, ChevronDown, AlertCircle, Clock, CheckCircle2 } from 'lucide-react';
import { Issue } from '@/lib/issue_types';

interface MobileTreeNodeProps {
  issue: Issue;
  /** ツリーの深さ（0始まり）。インデント量の計算に使用 */
  depth: number;
  hasChildren: boolean;
  isCollapsed: boolean;
  /** フィルタで非強調表示にするか */
  isDimmed: boolean;
  /** 自分に入ってくるエッジが存在する（= 何かに起因している） */
  hasIncoming: boolean;
  /** 自分から出ていくエッジが存在する（= 何かを引き起こしている） */
  hasOutgoing: boolean;
  onClick: () => void;
  onToggleCollapse: () => void;
}

/** カテゴリ別バッジ色 */
const CATEGORY_BADGE: Record<string, string> = {
  '工程': 'bg-blue-100 text-blue-700',
  'コスト': 'bg-yellow-100 text-yellow-700',
  '品質': 'bg-green-100 text-green-700',
  '安全': 'bg-red-100 text-red-700',
};

/**
 * ノード種別に応じた背景・ボーダー色を返す。
 * 根本原因: 入ってくるエッジなし + 出ていくエッジあり → 赤系
 * 中間原因: 両方あり → 橙系
 * 事象: 入ってくるエッジのみ or 孤立 → 青系
 */
function getNodeStyle(hasIncoming: boolean, hasOutgoing: boolean): string {
  if (!hasIncoming && hasOutgoing) return 'bg-red-50 border-red-200';
  if (hasIncoming && hasOutgoing) return 'bg-orange-50 border-orange-200';
  return 'bg-blue-50 border-blue-200';
}

/** ステータスに対応するアイコン */
function StatusIcon({ status }: { status: Issue['status'] }) {
  if (status === '解決済み') {
    return <CheckCircle2 size={14} className="text-green-500 flex-shrink-0" />;
  }
  if (status === '対応中') {
    return <Clock size={14} className="text-orange-400 flex-shrink-0" />;
  }
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
}: MobileTreeNodeProps) {
  // 1レベルにつき 20px インデント
  const indentPx = depth * 20;

  return (
    <div
      className={`flex items-stretch border-b border-gray-100 transition-opacity ${isDimmed ? 'opacity-30' : 'opacity-100'}`}
      style={{ paddingLeft: `${indentPx}px` }}
    >
      {/* 深さに応じた縦線（階層の視覚化） */}
      {depth > 0 && (
        <div className="w-px bg-gray-200 self-stretch mr-2 flex-shrink-0" />
      )}

      {/* 展開/折りたたみボタン（タッチターゲット: 44×44px） */}
      <button
        onClick={onToggleCollapse}
        className="flex-shrink-0 flex items-center justify-center w-[44px] min-h-[44px] text-gray-400 active:bg-gray-100"
        aria-label={isCollapsed ? '子課題を展開' : '子課題を折りたたむ'}
      >
        {hasChildren ? (
          isCollapsed
            ? <ChevronRight size={16} />
            : <ChevronDown size={16} />
        ) : (
          <span className="w-1.5 h-1.5 rounded-full bg-gray-300 inline-block" />
        )}
      </button>

      {/* ノード本体ボタン（タッチターゲット: min 44px） */}
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

        {/* カテゴリバッジ */}
        <span
          className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0 ${
            CATEGORY_BADGE[issue.category] ?? 'bg-gray-100 text-gray-600'
          }`}
        >
          {issue.category}
        </span>

        {/* critical は赤ドット */}
        {issue.priority === 'critical' && (
          <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
        )}
      </button>
    </div>
  );
}
