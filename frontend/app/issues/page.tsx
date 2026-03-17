'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, IssueEdge, CaptureResponse, IssuesListResponse } from '@/lib/issue_types';
import IssueFilterBar, { PriorityFilter } from '@/components/issues/IssueFilterBar';
import IssueChatPanel from '@/components/issues/IssueChatPanel';
import IssueCausalGraph from '@/components/issues/IssueCausalGraph';
import IssueDetailDrawer from '@/components/issues/IssueDetailDrawer';
import { ClipboardList, ArrowLeft, MessageCircle, Plus, ChevronRight, FolderOpen, Smartphone, Network } from 'lucide-react';
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
  const [creating, setCreating] = useState(false);

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
        <div className="ml-auto">
          <Link
            href="/issues/chat"
            className="flex items-center gap-1 text-xs text-blue-600 border border-blue-300 rounded px-2 py-1 hover:bg-blue-50"
          >
            <MessageCircle size={14} />
            チャット入力
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
// プロジェクト内グラフ画面
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
  const [activeTab, setActiveTab] = useState<'graph' | 'chat'>('graph');

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
        <button onClick={onBack} className="text-gray-400 hover:text-gray-700">
          <ArrowLeft size={18} />
        </button>
        <ClipboardList size={20} className="text-blue-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-semibold text-gray-800 truncate">{projectName}</h1>
        </div>
        <Link
          href={`/issues/capture?project=${encodeURIComponent(projectName)}`}
          className="flex items-center gap-1 text-xs text-blue-600 border border-blue-300 rounded px-2 py-1 hover:bg-blue-50 flex-shrink-0"
        >
          <Smartphone size={14} />
          モバイル入力
        </Link>
      </div>

      {/* フィルターバー（プロジェクト選択なし） */}
      <IssueFilterBar
        priorityFilter={priorityFilter}
        onPriorityFilter={setPriorityFilter}
        categoryFilter={categoryFilter}
        onCategoryFilter={setCategoryFilter}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* 左パネル: チャット入力 (デスクトップ専用) */}
        <div className="hidden md:flex md:flex-col w-72 flex-shrink-0 border-r border-gray-200 overflow-hidden">
          <IssueChatPanel
            projectName={projectName}
            issues={issues}
            onIssueAdded={handleIssueAdded}
          />
        </div>

        {/* グラフパネル (モバイルではグラフタブ選択時のみ表示) */}
        <div className={`flex-1 overflow-hidden relative ${activeTab === 'chat' ? 'hidden md:block' : 'block'}`}>
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
          />
        </div>

        {/* モバイル専用チャットパネル (チャットタブ選択時のみ表示) */}
        <div className={`md:hidden flex-1 overflow-hidden flex-col ${activeTab === 'graph' ? 'hidden' : 'flex'}`}>
          <IssueChatPanel
            projectName={projectName}
            issues={issues}
            onIssueAdded={handleIssueAdded}
          />
        </div>
      </div>

      {/* モバイル専用ボトムタブバー */}
      <div className="md:hidden flex border-t border-gray-200 bg-white flex-shrink-0">
        <button
          onClick={() => setActiveTab('graph')}
          className={`flex-1 py-3 flex flex-col items-center gap-0.5 text-xs transition-colors ${
            activeTab === 'graph' ? 'text-blue-600' : 'text-gray-400'
          }`}
        >
          <Network size={18} />
          グラフ
        </button>
        <button
          onClick={() => setActiveTab('chat')}
          className={`flex-1 py-3 flex flex-col items-center gap-0.5 text-xs transition-colors ${
            activeTab === 'chat' ? 'text-blue-600' : 'text-gray-400'
          }`}
        >
          <MessageCircle size={18} />
          チャット
        </button>
      </div>

      <IssueDetailDrawer
        issue={selectedIssue}
        onClose={() => setSelectedIssue(null)}
        onUpdated={handleIssueUpdated}
      />
    </div>
  );
}

// ────────────────────────────────────────────────
// ページエントリ
// ────────────────────────────────────────────────
export default function IssuesPage() {
  const [selectedProject, setSelectedProject] = useState<string | null>(null);

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
