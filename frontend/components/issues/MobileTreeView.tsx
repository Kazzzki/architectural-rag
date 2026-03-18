'use client';

/**
 * MobileTreeView.tsx
 * 課題因果グラフのモバイル用 Collapsible Vertical Tree ビュー。
 *
 * 設計方針:
 * - 外部ライブラリ追加なし（追加依存ゼロ）
 *   理由: issue + edge の型は既存そのままで、再帰的なツリー描画は
 *   Tailwind + React state で十分実現可能。バンドルサイズ増加を避けるため。
 * - ReactFlow の代替としてモバイル（≤768px）でのみ表示される
 * - 既存の issues / edges / priorityFilter props をそのまま受け取る
 *
 * ノード色の仕様:
 *   根本原因（自分への入力エッジなし、自分からの出力エッジあり）: 赤系
 *   中間原因（両方あり）: 橙系
 *   事象（入力エッジのみ、または孤立）: 青系
 */

import React, { useMemo, useState } from 'react';
import { Issue, IssueEdge } from '@/lib/issue_types';
import type { PriorityFilter } from './IssueFilterBar';
import MobileTreeNode from './MobileTreeNode';

interface MobileTreeViewProps {
  issues: Issue[];
  edges: IssueEdge[];
  priorityFilter: PriorityFilter;
  onNodeClick: (issue: Issue) => void;
}

/** ツリー構造の内部表現 */
interface TreeNode {
  issue: Issue;
  children: TreeNode[];
  hasIncoming: boolean;
  hasOutgoing: boolean;
}

/**
 * issues + edges から Collapsible Tree 構造を構築する。
 * エッジ方向: from_id (原因) → to_id (結果)
 * ルートノード = 入ってくるエッジがない issue（= 根本原因）
 * 孤立ノード（エッジなし）は別途返却される。
 */
function buildTree(
  issues: Issue[],
  edges: IssueEdge[]
): { roots: TreeNode[]; orphans: Issue[] } {
  const issueMap = new Map<string, Issue>(issues.map((i) => [i.id, i]));
  // from_id → to_id の隣接リスト
  const childrenOf = new Map<string, string[]>();
  // 各ノードへの入力エッジ数
  const inDegree = new Map<string, number>();

  issues.forEach((i) => {
    childrenOf.set(i.id, []);
    inDegree.set(i.id, 0);
  });

  edges.forEach((e) => {
    if (!issueMap.has(e.from_id) || !issueMap.has(e.to_id)) return;
    childrenOf.get(e.from_id)!.push(e.to_id);
    inDegree.set(e.to_id, (inDegree.get(e.to_id) ?? 0) + 1);
  });

  // 循環を防ぐ再帰ビルダー
  function buildNode(id: string, visited: Set<string>): TreeNode | null {
    if (visited.has(id)) return null;
    const issue = issueMap.get(id);
    if (!issue) return null;
    visited.add(id);

    const childIds = childrenOf.get(id) ?? [];
    const children = childIds
      .map((cid) => buildNode(cid, new Set(visited)))
      .filter(Boolean) as TreeNode[];

    return {
      issue,
      children,
      hasIncoming: (inDegree.get(id) ?? 0) > 0,
      hasOutgoing: childIds.length > 0,
    };
  }

  // エッジが全くないノード = 孤立
  const hasAnyEdge = new Set<string>();
  edges.forEach((e) => {
    hasAnyEdge.add(e.from_id);
    hasAnyEdge.add(e.to_id);
  });

  const orphans = issues.filter((i) => !hasAnyEdge.has(i.id));

  // ルート = 入力エッジ 0 かつ何らかのエッジを持つ
  const rootIds = issues
    .filter((i) => hasAnyEdge.has(i.id) && (inDegree.get(i.id) ?? 0) === 0)
    .map((i) => i.id);

  const roots = rootIds
    .map((id) => buildNode(id, new Set()))
    .filter(Boolean) as TreeNode[];

  return { roots, orphans };
}

export default function MobileTreeView({
  issues,
  edges,
  priorityFilter,
  onNodeClick,
}: MobileTreeViewProps) {
  // 折りたたまれたノードの ID セット
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());

  const { roots, orphans } = useMemo(
    () => buildTree(issues, edges),
    [issues, edges]
  );

  function toggleCollapse(id: string) {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  /** priorityFilter に応じて非強調表示かどうかを判定 */
  function isDimmed(issue: Issue): boolean {
    if (priorityFilter === 'critical') return issue.priority !== 'critical';
    if (priorityFilter === 'normal_up') return issue.priority === 'minor';
    return false;
  }

  /** ツリーノードを再帰的にレンダリング */
  function renderNodes(nodes: TreeNode[], depth: number): React.ReactNode {
    return nodes.map((node) => {
      const collapsed = collapsedIds.has(node.issue.id);
      return (
        <React.Fragment key={node.issue.id}>
          <MobileTreeNode
            issue={node.issue}
            depth={depth}
            hasChildren={node.children.length > 0}
            isCollapsed={collapsed}
            isDimmed={isDimmed(node.issue)}
            hasIncoming={node.hasIncoming}
            hasOutgoing={node.hasOutgoing}
            onClick={() => onNodeClick(node.issue)}
            onToggleCollapse={() => toggleCollapse(node.issue.id)}
          />
          {!collapsed && node.children.length > 0 && renderNodes(node.children, depth + 1)}
        </React.Fragment>
      );
    });
  }

  if (issues.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3 p-8">
        <span className="text-5xl">📋</span>
        <p className="text-sm font-medium">課題がありません</p>
        <p className="text-xs text-gray-300 text-center">
          下の「課題追加」ボタンから<br />課題を登録してください
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto pb-28">
      {/* 凡例（色の説明） */}
      <div className="flex items-center gap-4 px-4 py-2 text-[10px] text-gray-500 border-b border-gray-100 bg-gray-50">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm bg-red-100 border border-red-200 inline-block" />
          根本原因
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm bg-orange-100 border border-orange-200 inline-block" />
          中間原因
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm bg-blue-100 border border-blue-200 inline-block" />
          事象
        </span>
      </div>

      {/* 因果ツリー */}
      {roots.length > 0 && (
        <div className="divide-y divide-gray-50">
          {renderNodes(roots, 0)}
        </div>
      )}

      {/* 孤立ノード（エッジのない課題） */}
      {orphans.length > 0 && (
        <div>
          <div className="px-4 py-1.5 text-[10px] font-medium text-gray-400 bg-gray-50 border-y border-gray-100">
            未接続の課題
          </div>
          <div className="divide-y divide-gray-50">
            {orphans.map((issue) => (
              <MobileTreeNode
                key={issue.id}
                issue={issue}
                depth={0}
                hasChildren={false}
                isCollapsed={false}
                isDimmed={isDimmed(issue)}
                hasIncoming={false}
                hasOutgoing={false}
                onClick={() => onNodeClick(issue)}
                onToggleCollapse={() => {}}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
