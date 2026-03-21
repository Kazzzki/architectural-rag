'use client';

/**
 * MobileTreeView.tsx
 * 課題因果グラフのモバイル用 Collapsible Vertical Tree ビュー。
 *
 * 設計方針:
 * - 外部ライブラリ追加なし（追加依存ゼロ）
 * - ReactFlow の代替として、タッチ操作を奪わない純 CSS/React 実装
 * - 既存の issues / edges / priorityFilter props をそのまま受け取る
 * - incomingEdge コネクタをタップすると因果関係詳細モーダルを表示
 *
 * ノード色:
 *   根本原因（入力エッジなし・出力エッジあり）: 赤系
 *   中間原因（両方あり）: 橙系
 *   事象（入力エッジのみ・孤立）: 青系
 */

import React, { useMemo, useState } from 'react';
import { X, ArrowRight, CheckCircle2, AlertCircle } from 'lucide-react';
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

/** エッジ詳細モーダルに渡すコンテキスト */
interface EdgeContext {
  edge: IssueEdge;
  parentIssue: Issue;
  childIssue: Issue;
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
  const childrenOf = new Map<string, string[]>();
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

  const hasAnyEdge = new Set<string>();
  edges.forEach((e) => { hasAnyEdge.add(e.from_id); hasAnyEdge.add(e.to_id); });

  const orphans = issues.filter((i) => !hasAnyEdge.has(i.id));

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
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [selectedEdge, setSelectedEdge] = useState<EdgeContext | null>(null);

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

  function isDimmed(issue: Issue): boolean {
    if (priorityFilter === 'critical') return issue.priority !== 'critical';
    if (priorityFilter === 'normal_up') return issue.priority === 'minor';
    return false;
  }

  /** ツリーノードを再帰的にレンダリング。parentIssue でエッジ検索を行う */
  function renderNodes(nodes: TreeNode[], depth: number, parentIssue?: Issue): React.ReactNode {
    return nodes.map((node) => {
      const collapsed = collapsedIds.has(node.issue.id);

      // 親→このノードへのエッジを検索
      const incomingEdge = parentIssue
        ? edges.find((e) => e.from_id === parentIssue.id && e.to_id === node.issue.id)
        : undefined;

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
            incomingEdge={incomingEdge}
            onEdgeClick={
              incomingEdge && parentIssue
                ? () => setSelectedEdge({ edge: incomingEdge, parentIssue, childIssue: node.issue })
                : undefined
            }
          />
          {!collapsed && node.children.length > 0 &&
            renderNodes(node.children, depth + 1, node.issue)
          }
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
    <div className="h-full overflow-y-auto pb-28">
      {/* 凡例 */}
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

      {/* ─── エッジ詳細モーダル ─── */}
      {selectedEdge && (
        <div
          className="fixed inset-0 z-[70] flex flex-col bg-black/40 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedEdge(null); }}
        >
          <div className="mt-auto bg-white rounded-t-2xl shadow-2xl">
            {/* ヘッダー */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <h3 className="font-semibold text-gray-800 text-sm flex items-center gap-2">
                {selectedEdge.edge.confirmed
                  ? <><CheckCircle2 size={16} className="text-red-500" /> 確定した因果関係</>
                  : <><AlertCircle  size={16} className="text-gray-400" /> 仮設因果関係</>
                }
              </h3>
              <button
                onClick={() => setSelectedEdge(null)}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            {/* 本体 */}
            <div className="px-4 py-4 space-y-3">
              {/* 原因ノード */}
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide">原因</span>
                <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm font-medium text-gray-800">
                  {selectedEdge.parentIssue.title}
                </div>
              </div>

              {/* 矢印 */}
              <div className="flex items-center gap-2 px-2">
                <div className="flex-1 h-px bg-gray-200" />
                <div className="flex items-center gap-1.5">
                  <ArrowRight size={16} className={selectedEdge.edge.confirmed ? 'text-red-400' : 'text-gray-400'} />
                  <span className={`text-[9px] px-2 py-0.5 rounded-full font-semibold ${
                    selectedEdge.edge.confirmed
                      ? 'bg-red-100 text-red-600'
                      : 'bg-gray-100 text-gray-500'
                  }`}>
                    {selectedEdge.edge.confirmed ? '確定因果' : '仮設因果'}
                  </span>
                </div>
                <div className="flex-1 h-px bg-gray-200" />
              </div>

              {/* 結果ノード */}
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide">結果</span>
                <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 text-sm font-medium text-gray-800">
                  {selectedEdge.childIssue.title}
                </div>
              </div>

              {/* 登録日 */}
              <div className="text-[10px] text-gray-400 text-center pb-safe pb-2">
                登録日: {new Date(selectedEdge.edge.created_at).toLocaleDateString('ja-JP')}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
