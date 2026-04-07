'use client';

import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import {
  DndContext, DragEndEvent, DragOverEvent, DragOverlay, DragStartEvent,
  PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  Plus, X, Send, Clock, Calendar, CheckSquare, Loader2, Bot,
  LayoutGrid, GitBranch, List, Sun, FileText, ClipboardList, ArrowLeft,
} from 'lucide-react';

import type { Task, Category, Label, Milestone, ChatMessage } from './types';
import { STATUS_LABEL } from './types';
import { api } from './taskApi';

import TaskCard from './TaskCard';
import KanbanColumn from './KanbanColumn';
import CreateTaskModal from './CreateTaskModal';
import TaskDetailPanel from './TaskDetailPanel';
import TaskCalendar from './TaskCalendar';
import TaskTable from './TaskTable';
import TaskReport from './TaskReport';
import MeetingTaskExtractor from './MeetingTaskExtractor';
import TodayView from './TodayView';
import PortfolioDashboard from './PortfolioDashboard';
import WorkloadView from './WorkloadView';
import BottomNav from './BottomNav';
import QuickAddSheet from './QuickAddSheet';
import ProjectStatsBar from './ProjectStatsBar';

const TaskMindMap = lazy(() => import('./TaskMindMap'));

type ViewMode = 'today' | 'kanban' | 'table' | 'calendar' | 'mindmap' | 'portfolio' | 'workload';

const VIEWS: { key: ViewMode; icon: typeof Sun; label: string }[] = [
  { key: 'today', icon: Sun, label: '今日' },
  { key: 'kanban', icon: LayoutGrid, label: 'ボード' },
  { key: 'table', icon: List, label: 'リスト' },
  { key: 'calendar', icon: Calendar, label: 'カレンダー' },
  { key: 'mindmap', icon: GitBranch, label: 'マップ' },
  { key: 'portfolio', icon: FileText, label: 'PJ一覧' },
  { key: 'workload', icon: ClipboardList, label: '負荷' },
];

function TasksPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();

  // State
  const [tasks, setTasks] = useState<Task[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [showExtractor, setShowExtractor] = useState(false);
  const [showQuickAdd, setShowQuickAdd] = useState(false);
  const [showMoreMenu, setShowMoreMenu] = useState(false);

  // Filters from URL
  const [viewMode, setViewMode] = useState<ViewMode>((searchParams.get('view') as ViewMode) || 'today');
  const [filterProject, setFilterProject] = useState(searchParams.get('project') || '');
  const [filterCategory, setFilterCategory] = useState(searchParams.get('category') || '');
  const [filterPriority, setFilterPriority] = useState(searchParams.get('priority') || '');
  const [filterAssignee, setFilterAssignee] = useState(searchParams.get('assignee') || '');
  const [filterLabel, setFilterLabel] = useState(searchParams.get('label') || '');

  const [projects, setProjects] = useState<string[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [mobileColumn, setMobileColumn] = useState(0);

  // Quick add & chat
  const [quickInput, setQuickInput] = useState('');
  const [quickAdding, setQuickAdding] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  // URL sync
  useEffect(() => {
    const params = new URLSearchParams();
    if (viewMode !== 'today') params.set('view', viewMode);
    if (filterProject) params.set('project', filterProject);
    if (filterCategory) params.set('category', filterCategory);
    if (filterPriority) params.set('priority', filterPriority);
    if (filterAssignee) params.set('assignee', filterAssignee);
    if (filterLabel) params.set('label', filterLabel);
    const q = params.toString();
    router.replace(`/tasks${q ? `?${q}` : ''}`, { scroll: false });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, filterProject, filterCategory, filterPriority, filterAssignee, filterLabel]);

  // Data fetch
  const fetchTasks = useCallback(async () => {
    const filters: Record<string, string> = {};
    if (filterProject) filters.project_name = filterProject;
    if (filterCategory) filters.category_id = filterCategory;
    if (filterPriority) filters.priority = filterPriority;
    if (filterAssignee) filters.assignee_name = filterAssignee;
    if (filterLabel) filters.label_id = filterLabel;
    const data = await api.getTasks(filters);
    setTasks(data ?? []);
  }, [filterProject, filterCategory, filterPriority, filterAssignee, filterLabel]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      try {
        const [t, c, p, l, m] = await Promise.all([
          api.getTasks(),
          api.getCategories(),
          api.getProjects().catch(() => [] as string[]),
          api.getLabels().catch(() => []),
          api.getMilestones().catch(() => []),
        ]);
        setTasks(t ?? []);
        setCategories(c ?? []);
        setProjects(p ?? []);
        setLabels(l ?? []);
        setMilestones(m ?? []);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(`タスク取得エラー: ${msg}`);
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  // Reminder polling
  useEffect(() => {
    const check = async () => {
      try {
        const reminders = await api.getPendingReminders();
        for (const r of reminders ?? []) {
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification(`リマインダー: ${r.task_title}`, { body: r.message ?? r.remind_at });
          }
        }
      } catch (e) { console.warn('reminder poll:', e); }
    };
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission();
    }
    const interval = setInterval(check, 30_000);
    return () => clearInterval(interval);
  }, []);

  // DnD
  const activeTask = tasks.find((t) => t.id === activeId) ?? null;

  const handleDragStart = (e: DragStartEvent) => setActiveId(e.active.id as number);

  const handleDragOver = (e: DragOverEvent) => {
    const { active, over } = e;
    if (!over) return;
    const at = tasks.find((t) => t.id === active.id);
    if (!at) return;
    const overId = over.id as string | number;
    let targetStatus = at.status;
    if (typeof overId === 'string' && ['todo', 'in_progress', 'done'].includes(overId)) {
      targetStatus = overId as Task['status'];
    } else {
      const ot = tasks.find((t) => t.id === overId);
      if (ot) targetStatus = ot.status;
    }
    if (targetStatus !== at.status) {
      setTasks((prev) => prev.map((t) => (t.id === at.id ? { ...t, status: targetStatus as Task['status'] } : t)));
    }
  };

  const handleDragEnd = (e: DragEndEvent) => {
    const { active } = e;
    setActiveId(null);
    const dt = tasks.find((t) => t.id === active.id);
    if (dt) api.updateTask(dt.id, { status: dt.status }).catch(console.error);
  };

  // Filtered tasks
  const filteredTasks = tasks.filter((t) => {
    if (t.parent_id) return false; // hide subtasks from main views
    if (filterCategory && t.category_id?.toString() !== filterCategory) return false;
    if (filterPriority && t.priority !== filterPriority) return false;
    if (filterProject && t.project_name !== filterProject) return false;
    if (filterAssignee && t.assignee_name !== filterAssignee) return false;
    if (filterLabel && !t.label_ids?.split(',').includes(filterLabel)) return false;
    return true;
  });

  const columnTasks = (status: string) => filteredTasks.filter((t) => t.status === status);

  // Computed
  const doneTasks = tasks.filter((t) => t.status === 'done').length;
  const todayStr = new Date().toISOString().slice(0, 10);
  const todayTaskCount = tasks.filter((t) => t.due_date?.slice(0, 10) === todayStr).length;
  const assigneeNames = [...new Set(tasks.map((t) => t.assignee_name).filter(Boolean))] as string[];

  // Handlers
  const handleToggleDone = async (task: Task) => {
    const newStatus = task.status === 'done' ? 'todo' : 'done';
    setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: newStatus as Task['status'] } : t));
    api.updateTask(task.id, { status: newStatus }).catch(() => {
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: task.status } : t));
    });
  };

  const handleQuickAdd = async () => {
    const title = quickInput.trim();
    if (!title || quickAdding) return;
    setQuickAdding(true);
    setQuickInput('');
    try {
      const task = await api.createTask({ title, status: 'todo', priority: 'medium', project_name: filterProject || undefined });
      setTasks((prev) => [task, ...prev]);
    } catch {
      setQuickInput(title);
    } finally {
      setQuickAdding(false);
    }
  };

  const handleChatSubmit = async () => {
    if (!chatInput.trim() || chatLoading) return;
    const msg = chatInput.trim();
    setChatInput('');
    setChatMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setChatLoading(true);
    try {
      const result = await api.chat(msg);
      setChatMessages((prev) => [...prev, { role: 'ai', content: result.message ?? '完了しました' }]);
      fetchTasks();
    } catch (err) {
      setChatMessages((prev) => [...prev, { role: 'ai', content: `エラー: ${err}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  const switchView = (mode: ViewMode) => {
    setViewMode(mode);
    setSelectedTaskId(null);
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-3 md:px-6 py-2 md:py-3 flex-shrink-0">
        <div className="max-w-7xl mx-auto space-y-1 md:space-y-2">
          <div className="flex items-center gap-3">
            <button onClick={() => router.back()} className="p-1.5 rounded-full hover:bg-gray-100 text-gray-500 shrink-0" aria-label="戻る">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <CheckSquare className="w-5 h-5 text-gray-900 shrink-0" />
            <h1 className="text-lg font-bold text-gray-900 shrink-0">タスク管理</h1>
            <div className="hidden md:flex flex-wrap gap-3 text-xs text-gray-500 ml-1">
              <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" />今日 {todayTaskCount}件</span>
              <span className="flex items-center gap-1"><CheckSquare className="w-3.5 h-3.5" />完了 {doneTasks}/{tasks.length}</span>
            </div>
            <div className="flex gap-2 ml-auto shrink-0">
              <select value={filterProject} onChange={(e) => setFilterProject(e.target.value)}
                className="px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white max-w-[120px] truncate">
                <option value="">全PJ</option>
                {projects.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              {assigneeNames.length > 0 && (
                <select value={filterAssignee} onChange={(e) => setFilterAssignee(e.target.value)}
                  className="hidden sm:block px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white max-w-[100px]">
                  <option value="">全担当</option>
                  {assigneeNames.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              )}
              <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}
                className="hidden sm:block px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                <option value="">全カテゴリ</option>
                {categories.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
              </select>
              <select value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)}
                className="hidden sm:block px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                <option value="">全優先度</option>
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
              <button onClick={() => setShowCreateModal(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 text-white text-sm font-medium rounded-full hover:bg-gray-700">
                <Plus className="w-4 h-4" /><span className="hidden sm:inline">タスク追加</span>
              </button>
            </div>
          </div>

          {/* View tabs + action buttons (hidden on mobile — use BottomNav) */}
          <div className="hidden md:flex items-center gap-3">
            <div className="flex items-center gap-0.5 bg-gray-100 rounded-full p-0.5">
              {VIEWS.map(({ key, icon: Icon, label }) => (
                <button key={key} onClick={() => switchView(key)}
                  className={`flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    viewMode === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}>
                  <Icon className="w-3.5 h-3.5" />{label}
                </button>
              ))}
            </div>
            <div className="flex gap-1.5 ml-auto">
              <button onClick={() => setShowReport(true)}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 rounded-full hover:bg-gray-200">
                <FileText className="w-3.5 h-3.5" />レポート
              </button>
              <button onClick={() => setShowExtractor(true)}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 rounded-full hover:bg-gray-200">
                <ClipboardList className="w-3.5 h-3.5" />議事録→タスク
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Quick add (hidden on mobile — use FAB) */}
      <div className="hidden md:block bg-white border-b border-gray-100 px-4 md:px-6 py-2">
        <div className="max-w-7xl mx-auto flex gap-2 items-center">
          <input type="text" value={quickInput} onChange={(e) => setQuickInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); handleQuickAdd(); } }}
            placeholder="タスクを追加... (Enter で即追加)"
            className="flex-1 px-3 py-2 rounded-full border border-gray-200 text-sm bg-gray-50"
            disabled={quickAdding} />
          <button onClick={handleQuickAdd} disabled={!quickInput.trim() || quickAdding}
            className="px-3 py-2 bg-gray-900 text-white rounded-full hover:bg-gray-700 disabled:opacity-30 shrink-0">
            {quickAdding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Project stats bar (when filtering by project) */}
      {filterProject && <ProjectStatsBar tasks={tasks} projectName={filterProject} />}

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 overflow-auto p-4 md:p-6">
          {loading ? (
            <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
          ) : error ? (
            <div className="flex flex-col justify-center items-center h-64 gap-3">
              <p className="text-gray-700 text-sm">{error}</p>
              <button onClick={() => { setError(null); setLoading(true); }} className="text-xs text-gray-500 underline">再試行</button>
            </div>
          ) : viewMode === 'today' ? (
            <TodayView tasks={filteredTasks} onTaskClick={(t) => setSelectedTaskId(t.id)} onToggleDone={handleToggleDone} />
          ) : viewMode === 'kanban' ? (
            <DndContext sensors={sensors} onDragStart={handleDragStart} onDragOver={handleDragOver} onDragEnd={handleDragEnd}>
              <div className="md:hidden max-w-7xl mx-auto">
                {/* Snap-scroll kanban columns */}
                <div className="flex overflow-x-auto snap-x snap-mandatory gap-3 -mx-3 px-3 pb-2"
                  style={{ scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}>
                  {(['todo', 'in_progress', 'done'] as const).map((status) => (
                    <div key={status} className="snap-start shrink-0" style={{ width: '85vw' }}>
                      <KanbanColumn status={status} tasks={columnTasks(status)}
                        onTaskClick={(t) => setSelectedTaskId(t.id)} onToggleDone={handleToggleDone} />
                    </div>
                  ))}
                </div>
              </div>
              <div className="hidden md:flex flex-row gap-4 max-w-7xl mx-auto">
                {(['todo', 'in_progress', 'done'] as const).map((status) => (
                  <KanbanColumn key={status} status={status} tasks={columnTasks(status)}
                    onTaskClick={(t) => setSelectedTaskId(t.id)} onToggleDone={handleToggleDone} />
                ))}
              </div>
              <DragOverlay>{activeTask && <TaskCard task={activeTask} overlay />}</DragOverlay>
            </DndContext>
          ) : viewMode === 'table' ? (
            <TaskTable tasks={filteredTasks} onTaskClick={(t) => setSelectedTaskId(t.id)}
              onToggleDone={handleToggleDone} onRefresh={fetchTasks} />
          ) : viewMode === 'portfolio' ? (
            <PortfolioDashboard />
          ) : viewMode === 'workload' ? (
            <WorkloadView />
          ) : viewMode === 'calendar' ? (
            <TaskCalendar tasks={filteredTasks} onSelect={(id) => setSelectedTaskId(id)} />
          ) : (
            <Suspense fallback={<div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>}>
              <TaskMindMap tasks={filteredTasks} onSelect={(id) => setSelectedTaskId(id)} />
            </Suspense>
          )}
        </div>

        {selectedTaskId != null && (
          <TaskDetailPanel
            taskId={selectedTaskId} categories={categories} projects={projects}
            labels={labels} milestones={milestones}
            onClose={() => setSelectedTaskId(null)}
            onUpdate={(updated) => { setTasks((prev) => prev.map((t) => (t.id === updated.id ? { ...t, ...updated } : t))); }}
            onDelete={(id) => { setTasks((prev) => prev.filter((t) => t.id !== id)); setSelectedTaskId(null); }}
          />
        )}
      </div>

      {/* AI Chat bar (hidden on mobile — use BottomNav) */}
      <div className="hidden md:block bg-white border-t border-gray-200 px-4 md:px-6 py-3 flex-shrink-0">
        <div className="max-w-7xl mx-auto">
          {chatMessages.length > 0 && (
            <div className="mb-2 max-h-32 overflow-y-auto space-y-1">
              {chatMessages.slice(-4).map((m, i) => (
                <div key={i} className={`text-xs py-1 pl-3 ${
                  m.role === 'user' ? 'border-l-2 border-gray-300 text-gray-900' : 'border-l-2 border-gray-100 text-gray-500'
                }`}>{m.content}</div>
              ))}
            </div>
          )}
          <div className="flex gap-2 items-center">
            <Bot className="w-5 h-5 text-gray-400 flex-shrink-0" />
            <input type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChatSubmit(); } }}
              placeholder="「明日の会議をリマインドして」「設計レビューのタスクを追加して」"
              className="flex-1 px-3 py-2 rounded-full border border-gray-200 text-sm bg-white"
              disabled={chatLoading} />
            <button onClick={handleChatSubmit} disabled={!chatInput.trim() || chatLoading}
              className="px-4 py-2 bg-gray-900 text-white rounded-full hover:bg-gray-700 disabled:opacity-50 flex-shrink-0">
              {chatLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>

      {/* Modals */}
      {showCreateModal && (
        <CreateTaskModal categories={categories} projects={projects} labels={labels} milestones={milestones}
          defaultProject={filterProject}
          onClose={() => setShowCreateModal(false)}
          onCreate={(task) => { setTasks((prev) => [task, ...prev]); setShowCreateModal(false); }} />
      )}
      {showReport && <TaskReport projects={projects} onClose={() => setShowReport(false)} />}
      {showExtractor && (
        <MeetingTaskExtractor
          onClose={() => setShowExtractor(false)}
          onCreated={() => { setShowExtractor(false); fetchTasks(); }} />
      )}

      {/* Mobile Quick Add Sheet (vaul) */}
      <QuickAddSheet
        open={showQuickAdd}
        onOpenChange={setShowQuickAdd}
        onCreated={(task) => { setTasks((prev) => [task, ...prev]); }}
        defaultProject={filterProject}
      />

      {/* Mobile Bottom Nav */}
      <BottomNav
        activeTab={viewMode}
        onTabChange={(tab) => switchView(tab as ViewMode)}
        onAdd={() => setShowQuickAdd(true)}
        onMoreOpen={() => setShowMoreMenu(!showMoreMenu)}
      />

      {/* Mobile More Menu */}
      {showMoreMenu && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={() => setShowMoreMenu(false)}>
          <div className="absolute bottom-16 right-4 bg-white rounded-lg shadow-xl border border-gray-200 py-2 min-w-[160px]"
            onClick={(e) => e.stopPropagation()}>
            {VIEWS.map(({ key, icon: Icon, label }) => (
              <button key={key} onClick={() => { switchView(key); setShowMoreMenu(false); }}
                className={`w-full flex items-center gap-2 px-4 py-2.5 text-sm ${
                  viewMode === key ? 'text-gray-900 font-medium bg-gray-50' : 'text-gray-600'
                }`}>
                <Icon className="w-4 h-4" />{label}
              </button>
            ))}
            <div className="border-t border-gray-100 mt-1 pt-1">
              <button onClick={() => { setShowReport(true); setShowMoreMenu(false); }}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-gray-600">
                <FileText className="w-4 h-4" />レポート
              </button>
              <button onClick={() => { setShowExtractor(true); setShowMoreMenu(false); }}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-gray-600">
                <ClipboardList className="w-4 h-4" />議事録→タスク
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mobile bottom padding for nav */}
      <div className="h-16 md:hidden" />
    </div>
  );
}

export default function TasksPage() {
  return (
    <Suspense fallback={<div className="flex justify-center items-center h-screen"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>}>
      <TasksPageInner />
    </Suspense>
  );
}
