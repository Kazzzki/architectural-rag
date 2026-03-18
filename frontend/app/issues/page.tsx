'use client';

import React, { Suspense, useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { authFetch } from '@/lib/api';
import { Issue, IssueEdge, CaptureResponse, IssuesListResponse } from '@/lib/issue_types';
import IssueFilterBar, { PriorityFilter } from '@/components/issues/IssueFilterBar';
import IssueChatPanel from '@/components/issues/IssueChatPanel';
import IssueCausalGraph from '@/components/issues/IssueCausalGraph';
import IssueDetailDrawer from '@/components/issues/IssueDetailDrawer';
import { ClipboardList, ArrowLeft, MessageCircle, Plus, ChevronRight, FolderOpen, Filter, Maximize2, X, Map, Smartphone } from 'lucide-react';
import Link from 'next/link';

// ────────────────────────────────────────────────
// プロジェクト一覧画面
// ────────────────────────────────────────────────
function ProjectListView({
  onSelect,
}: {
  onSelect: (name: string) => void;
}) {
  const [projects, setProjects] = useState<{ name: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState('');

  useEffect(() => {
    authFetch('/api/issues')
      .then((r) => r.json())
      .then((data: IssuesListResponse) => {
        const counts: Record<string, number> = {};
        data.issues.forEach((iss) => {
          counts[iss.project_name] = (counts[iss.project_name] ?? 0) + 1;
        });
        setProjects(data.projects.map((name) => ({ name, count: counts[name] ?? 0 })));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function handleCreate() {
    const trimmed = newName.trim();
    if (!trimmed) return;
    onSelect(trimmed);
  }

  return (
    <div className="flex flex-col h-screen bg-white overflow-hidden">
      {/* ヘッダー */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 bg-white">
        <Link href="/" className="text-gray-400 hover:text-gray-700">
          <ArrowLeft size={18} />
        </Link>
        <ClipboardList size={20} className="text-blue-600" />
        <h1 className="text-base font-semibold text-gray-800">課題因果グラフ</h1>
        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/mindmap"
            className="flex items-center gap-1 text-xs text-violet-600 border border-violet-300 rounded px-2 py-1 hover:bg-violet-50"
          >
            <Map size={14} />
            マインドマップ
          </Link>
          <Link
            href="/issues/mobile"
            className="flex items-center gap-1 text-xs text-gray-500 border border-gray-300 rounded px-2 py-1 hover:bg-gray-50"
          >
            <Smartphone size={14} />
            スマホ表示
          </Link>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 max-w-xl mx-auto w-full">
        <h2 className="text-sm font-semibold text-gray-500 mb-4">プロジェクトを選択</h2>

        {loading && (
          <div className="text-sm text-gray-400 py-8 text-center">読み込み中…</div>
        )}

        {/* プロジェクトカード一覧 */}
        <div className="space-y-2 mb-6">
          {projects.map(({ name, count }) => (
            <button
              key={name}
              onClick={() => onSelect(name)}
              className="w-full flex items-center gap-3 px-4 py-3 bg-white border border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50 transition-colors text-left group"
            >
              <FolderOpen size={18} className="text-blue-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-800 truncate">{name}</div>
                <div className="text-xs text-gray-400">{count}件の課題</div>
              </div>
              <ChevronRight size={16} className="text-gray-300 group-hover:text-blue-400 flex-shrink-0" />
            </button>
          ))}

          {!loading && projects.length === 0 && (
            <div className="text-sm text-gray-400 py-6 text-center">
              まだプロジェクトがありません
            </div>
          )}
        </div>

        {/* 新規プロジェクト作成 */}
        <div className="border border-dashed border-gray-300 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Plus size={16} className="text-gray-400" />
            <span className="text-sm font-medium text-gray-600">新規プロジェクト</span>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              placeholder="プロジェクト名を入力…"
              className="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <button
              onClick={handleCreate}
              disabled={!newName.trim()}
              className="text-sm bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700 disabled:opacity-40 transition-colors"
            >
              作成
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────
// プロジェクト内グラフ画面（PC専用）
// ────────────────────────────────────────────────
function ProjectGraphView({
  projectName,
  onBack,
}: {
  projectName: string;
  onBack: () => void;
}) {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [edges, setEdges] = useState<IssueEdge[]>([]);
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>('all');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [loading, setLoading] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<'none' | 'chat' | 'filter'>('none');
  const [fitViewTrigger, setFitViewTrigger] = useState(0);

  const fetchIssues = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ project_name: projectName });
      if (categoryFilter) params.set('category', categoryFilter);
      const res = await authFetch(`/api/issues?${params.toString()}`);
      if (!res.ok) return;
      const data: IssuesListResponse = await res.json();
      setIssues(data.issues);
      setEdges(data.edges);
    } finally {
      setLoading(false);
    }
  }, [projectName, categoryFilter]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues]);

  function handleIssueAdded(resp: CaptureResponse) {
    if (resp.issue) {
      setIssues((prev) =>
        prev.find((iss) => iss.id === resp.issue.id) ? prev : [...prev, resp.issue]
      );
    }
    fetchIssues();
  }

  function handleIssueUpdated(updated: Issue) {
    setIssues((prev) => prev.map((iss) => (iss.id === updated.id ? updated : iss)));
    if (selectedIssue?.id === updated.id) setSelectedIssue(updated);
  }

  return (
    <div className="flex flex-col h-screen bg-white overflow-hidden">
      {/* ヘッダー */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 bg-white z-10">
        <button onClick={onBack} className="text-gray-400 hover:text-gray-700 flex-shrink-0">
          <ArrowLeft size={18} />
        </button>
        <ClipboardList size={20} className="text-blue-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-semibold text-gray-800 truncate">{projectName}</h1>
        </div>
        {/* ナビゲーション */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link
            href={`/issues/mobile?project=${encodeURIComponent(projectName)}`}
            className="flex items-center gap-1 text-xs text-gray-500 border border-gray-300 rounded px-2 py-1 hover:bg-gray-50"
            title="スマホ用ツリー表示"
          >
            <Smartphone size={13} />
            <span className="hidden sm:inline">スマホ表示</span>
          </Link>
          <Link
            href="/mindmap"
            className="flex items-center gap-1 text-xs text-violet-600 border border-violet-300 rounded px-2 py-1 hover:bg-violet-50"
            title="マインドマップへ"
          >
            <Map size={13} />
            <span className="hidden sm:inline">マインドマップ</span>
          </Link>
        </div>
      </div>

      {/* フィルターバー（デスクトップのみ） */}
      <div className="hidden md:block">
        <IssueFilterBar
          priorityFilter={priorityFilter}
          onPriorityFilter={setPriorityFilter}
          categoryFilter={categoryFilter}
          onCategoryFilter={setCategoryFilter}
        />
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* 左パネル: チャット入力（デスクトップのみ） */}
        <div className="hidden md:flex w-72 flex-shrink-0 border-r border-gray-200 flex-col overflow-hidden">
          <IssueChatPanel
            projectName={projectName}
            issues={issues}
            onIssueAdded={handleIssueAdded}
          />
        </div>

        {/* グラフエリア（PC専用 ReactFlow） */}
        <div className="flex-1 overflow-hidden relative">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white bg-opacity-60 z-10">
              <span className="text-sm text-gray-400">読み込み中…</span>
            </div>
          )}
          <IssueCausalGraph
            issues={issues}
            edges={edges}
            priorityFilter={priorityFilter}
            onNodeClick={setSelectedIssue}
            onRefresh={fetchIssues}
            fitViewTrigger={fitViewTrigger}
          />
        </div>
      </div>

      {/* モバイル専用底部バー */}
      <div className="md:hidden fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 p-1 bg-white/90 backdrop-blur border border-gray-200 rounded-2xl shadow-2xl">
        <button
          onClick={() => setMobilePanel(mobilePanel === 'chat' ? 'none' : 'chat')}
          className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all ${
            mobilePanel === 'chat' ? 'bg-blue-600 text-white shadow-inner' : 'text-gray-500 hover:bg-gray-50'
          }`}
        >
          <MessageCircle size={20} />
          <span className="text-[9px] font-bold">課題追加</span>
        </button>
        <button
          onClick={() => setMobilePanel(mobilePanel === 'filter' ? 'none' : 'filter')}
          className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all ${
            mobilePanel === 'filter' ? 'bg-blue-600 text-white shadow-inner' : 'text-gray-500 hover:bg-gray-50'
          }`}
        >
          <Filter size={20} />
          <span className="text-[9px] font-bold">フィルタ</span>
        </button>
        <div className="w-px h-8 bg-gray-200 mx-1" />
        <button
          onClick={() => setFitViewTrigger((v) => v + 1)}
          className="flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all text-gray-500 hover:bg-gray-50"
        >
          <Maximize2 size={20} />
          <span className="text-[9px] font-bold">全体表示</span>
        </button>
        <div className="w-px h-8 bg-gray-200 mx-1" />
        <Link
          href={`/issues/mobile?project=${encodeURIComponent(projectName)}`}
          className="flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all text-gray-500 hover:bg-gray-50"
        >
          <Smartphone size={20} />
          <span className="text-[9px] font-bold">リスト表示</span>
        </Link>
      </div>

      {/* モバイル ボトムシート */}
      {mobilePanel !== 'none' && (
        <div
          className="md:hidden fixed inset-0 z-[60] flex flex-col bg-black/40 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setMobilePanel('none'); }}
        >
          <div className="mt-auto bg-white rounded-t-2xl shadow-2xl max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2 text-sm">
                {mobilePanel === 'chat' && <><MessageCircle size={16} className="text-blue-600" /> 課題を追加</>}
                {mobilePanel === 'filter' && <><Filter size={16} className="text-blue-600" /> フィルター</>}
              </h3>
              <button
                onClick={() => setMobilePanel('none')}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {mobilePanel === 'chat' && (
                <IssueChatPanel
                  projectName={projectName}
                  issues={issues}
                  onIssueAdded={(resp) => { handleIssueAdded(resp); setMobilePanel('none'); }}
                />
              )}
              {mobilePanel === 'filter' && (
                <div className="p-4">
                  <IssueFilterBar
                    priorityFilter={priorityFilter}
                    onPriorityFilter={setPriorityFilter}
                    categoryFilter={categoryFilter}
                    onCategoryFilter={setCategoryFilter}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <IssueDetailDrawer
        issue={selectedIssue}
        onClose={() => setSelectedIssue(null)}
        onUpdated={handleIssueUpdated}
      />
    </div>
  );
}

// ────────────────────────────────────────────────
// ページエントリ（URLパラメータ対応）
// ────────────────────────────────────────────────
function IssuesContent() {
  const searchParams = useSearchParams();
  const initialProject = searchParams.get('project');
  const [selectedProject, setSelectedProject] = useState<string | null>(initialProject);

  if (selectedProject === null) {
    return <ProjectListView onSelect={setSelectedProject} />;
  }

  return (
    <ProjectGraphView
      projectName={selectedProject}
      onBack={() => setSelectedProject(null)}
    />
  );
}

export default function IssuesPage() {
  return (
    <Suspense>
      <IssuesContent />
    </Suspense>
  );
}
