'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../lib/api';
import { ReactFlowProvider } from 'reactflow';
import MindmapCanvas from '../components/mindmap/MindmapCanvas';
import GoalSearchBar from '../components/mindmap/GoalSearchBar';
import { Building2, ArrowLeft, Plus, Trash2, Clock, Target, ChevronDown, Eye, FolderOpen, Layers, ClipboardList, Upload, RefreshCw, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { CATEGORY_COLORS } from '@/lib/mindmapConstants';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

interface ProjectItem {
    id: string;
    name: string;
    description: string;
    template_id: string;
    building_type: string;
    status: string;
    created_at: string;
    updated_at: string;
    delta_count: number;
    progress: {
        total: number;
        completed: number;
        in_progress: number;
        percent: number;
    };
}

interface TemplateListItem {
    id: string;
    name: string;
    description: string;
    node_count: number;
    edge_count: number;
}

interface TemplateDetail {
    id: string;
    name: string;
    description: string;
    nodes: any[];
    edges: any[];
}


export default function MindmapDashboard() {
    const router = useRouter();
    const [projects, setProjects] = useState<ProjectItem[]>([]);
    const [templates, setTemplates] = useState<TemplateListItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'projects' | 'templates'>('projects');
    const [showCreateDialog, setShowCreateDialog] = useState(false);
    const [previewTemplate, setPreviewTemplate] = useState<TemplateDetail | null>(null);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

    // 課題→マインドマップ変換
    const [showFromIssuesDialog, setShowFromIssuesDialog] = useState(false);
    const [issueProjects, setIssueProjects] = useState<{ name: string; count: number }[]>([]);
    const [convertingIssues, setConvertingIssues] = useState(false);

    // Md→マインドマップ
    const mdFileInputRef = React.useRef<HTMLInputElement>(null);
    const [mdUploading, setMdUploading] = useState(false);

    // 課題プロジェクト一覧を取得
    const loadIssueProjects = useCallback(async () => {
        try {
            const res = await authFetch('/api/issues');
            if (res.ok) {
                const data = await res.json();
                const counts: Record<string, number> = {};
                (data.issues || []).forEach((iss: { project_name: string }) => {
                    counts[iss.project_name] = (counts[iss.project_name] ?? 0) + 1;
                });
                setIssueProjects(
                    (data.projects || []).map((name: string) => ({ name, count: counts[name] ?? 0 }))
                );
            }
        } catch {}
    }, []);

    // 課題→マインドマップ変換実行
    async function handleConvertFromIssues(projectName: string) {
        setConvertingIssues(true);
        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/from-issues?project_name=${encodeURIComponent(projectName)}`, {
                method: 'POST',
            });
            if (res.ok) {
                const data = await res.json();
                setShowFromIssuesDialog(false);
                router.push(`/mindmap/projects/${data.project_id}`);
            } else {
                const err = await res.json().catch(() => ({}));
                alert(err.detail || '変換に失敗しました');
            }
        } catch (e) {
            alert('変換エラーが発生しました');
        } finally {
            setConvertingIssues(false);
        }
    }

    // Mdアップロード→マインドマップ変換
    async function handleMdUpload(e: React.ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0];
        if (!file) return;
        setMdUploading(true);
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('project_name', file.name.replace(/\.(md|txt|markdown)$/i, ''));
            const res = await authFetch(`${API_BASE}/api/mindmap/from-markdown`, {
                method: 'POST',
                body: formData,
            });
            if (res.ok) {
                const data = await res.json();
                router.push(`/mindmap/projects/${data.project_id}`);
            } else {
                const err = await res.json().catch(() => ({}));
                alert(err.detail || 'Md変換に失敗しました');
            }
        } catch {
            alert('アップロードエラーが発生しました');
        } finally {
            setMdUploading(false);
            e.target.value = '';
        }
    }

    // Fetch data
    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const [projRes, tmplRes] = await Promise.all([
                authFetch(`${API_BASE}/api/mindmap/projects`),
                authFetch(`${API_BASE}/api/mindmap/templates`),
            ]);
            if (projRes.ok) setProjects(await projRes.json());
            if (tmplRes.ok) setTemplates(await tmplRes.json());
        } catch (err) {
            console.error('Projects load error:', err);
            setLoading(false);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadData();
    }, [loadData]);

    // 課題ダイアログが開いたら課題プロジェクト一覧を取得
    useEffect(() => {
        if (showFromIssuesDialog) loadIssueProjects();
    }, [showFromIssuesDialog, loadIssueProjects]);

    // Create project
    const handleCreateProject = async (name: string, templateId: string, buildingType: string) => {
        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/projects`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, template_id: templateId, building_type: buildingType }),
            });
            if (res.ok) {
                const data = await res.json();
                router.push(`/mindmap/projects/${data.id}`);
            }
        } catch (err) {
            console.error('Create error:', err);
        }
    };

    // Delete project
    const handleDeleteProject = async (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        if (!confirm('このプロジェクトを削除しますか？')) return;
        try {
            await authFetch(`${API_BASE}/api/mindmap/projects/${id}`, { method: 'DELETE' });
            loadData();
        } catch (err) {
            console.error('Delete error:', err);
        }
    };

    // Preview template
    const handlePreviewTemplate = async (templateId: string) => {
        try {
            const res = await authFetch(`${API_BASE}/api/mindmap/templates/${templateId}`);
            if (res.ok) setPreviewTemplate(await res.json());
        } catch (err) {
            console.error('Preview error:', err);
        }
    };

    const formatDate = (iso: string) => {
        const d = new Date(iso);
        return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
    };

    return (
        <div className="min-h-screen bg-[var(--background)]">
            {/* Header */}
            <header className="border-b border-[var(--border)] bg-white/80 backdrop-blur-sm sticky top-0 z-50">
                <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Link href="/" className="flex items-center gap-2 text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                            <ArrowLeft className="w-4 h-4" />
                            <span className="text-sm">RAG検索</span>
                        </Link>
                        <div className="w-px h-6 bg-[var(--border)]" />
                        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
                            <Building2 className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-[var(--foreground)]">
                                設計プロセスマップ
                            </h1>
                            <p className="text-[10px] text-[var(--muted)]">プロジェクトダッシュボード</p>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        {/* 課題→マインドマップ変換 */}
                        <button
                            onClick={() => setShowFromIssuesDialog(true)}
                            className="flex items-center gap-2 px-4 py-2 bg-white border border-emerald-200 text-emerald-600 rounded-lg text-sm font-medium hover:bg-emerald-50 transition-all shadow-sm"
                        >
                            <RefreshCw className="w-4 h-4" />
                            課題→マップ
                        </button>
                        {/* Mdアップロード→マインドマップ */}
                        <button
                            onClick={() => mdFileInputRef.current?.click()}
                            disabled={mdUploading}
                            className="flex items-center gap-2 px-4 py-2 bg-white border border-amber-200 text-amber-600 rounded-lg text-sm font-medium hover:bg-amber-50 transition-all shadow-sm disabled:opacity-50"
                        >
                            {mdUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                            {mdUploading ? 'AI分析中...' : 'Mdから作成'}
                        </button>
                        <input
                            ref={mdFileInputRef}
                            type="file"
                            accept=".md,.txt,.markdown"
                            className="hidden"
                            onChange={handleMdUpload}
                        />
                        <Link
                            href="/issues"
                            className="flex items-center gap-2 px-4 py-2 bg-white border border-blue-200 text-blue-600 rounded-lg text-sm font-medium hover:bg-blue-50 transition-all shadow-sm"
                        >
                            <ClipboardList className="w-4 h-4" />
                            課題因果グラフ
                        </Link>
                        <Link
                            href="/mindmap/local"
                            className="flex items-center gap-2 px-4 py-2 bg-white border border-[var(--border)] text-[var(--foreground)] rounded-lg text-sm font-medium hover:bg-gray-50 transition-all shadow-sm"
                        >
                            <FolderOpen className="w-4 h-4" />
                            ローカルフォルダを開く
                        </Link>
                        <button
                            onClick={() => setShowCreateDialog(true)}
                            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 text-white rounded-lg text-sm font-medium transition-all shadow-lg shadow-violet-500/25 hover:shadow-violet-500/40"
                        >
                            <Plus className="w-4 h-4" />
                            新規プロジェクト
                        </button>
                    </div>
                </div>
            </header>

            <main className="max-w-6xl mx-auto px-6 py-6">
                {/* Tabs */}
                <div className="flex gap-1 mb-6 bg-[var(--card)] rounded-lg p-1 w-fit">
                    <button
                        onClick={() => { setActiveTab('projects'); setPreviewTemplate(null); }}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'projects'
                            ? 'bg-violet-50 text-violet-700 shadow-sm'
                            : 'text-[var(--muted)] hover:text-[var(--foreground)]'
                            }`}
                    >
                        <FolderOpen className="w-4 h-4" />
                        プロジェクト ({projects.length})
                    </button>
                    <button
                        onClick={() => setActiveTab('templates')}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'templates'
                            ? 'bg-violet-50 text-violet-700 shadow-sm'
                            : 'text-[var(--muted)] hover:text-[var(--foreground)]'
                            }`}
                    >
                        <Layers className="w-4 h-4" />
                        テンプレート ({templates.length})
                    </button>
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-20">
                        <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                ) : activeTab === 'projects' ? (
                    /* Projects Tab */
                    <div>
                        {projects.length === 0 ? (
                            <div className="text-center py-20">
                                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[var(--card)] flex items-center justify-center">
                                    <FolderOpen className="w-8 h-8 text-[var(--muted)]" />
                                </div>
                                <h3 className="text-lg font-medium mb-2">プロジェクトがありません</h3>
                                <p className="text-[var(--muted)] text-sm mb-6">テンプレートからプロジェクトを作成して始めましょう</p>
                                <button
                                    onClick={() => setShowCreateDialog(true)}
                                    className="px-6 py-2.5 bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white rounded-lg text-sm font-medium"
                                >
                                    最初のプロジェクトを作成
                                </button>
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {projects.map(project => (
                                    <div
                                        key={project.id}
                                        onClick={() => router.push(`/mindmap/projects/${project.id}`)}
                                        className="group bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 cursor-pointer hover:border-violet-400 hover:shadow-lg hover:shadow-violet-100 transition-all"
                                    >
                                        <div className="flex items-start justify-between mb-2">
                                            <div>
                                                <h3 className="font-semibold text-[var(--foreground)] group-hover:text-violet-700 transition-colors">
                                                    {project.name}
                                                </h3>
                                                <p className="text-xs text-[var(--muted)] mt-0.5 line-clamp-1">{project.description}</p>
                                            </div>
                                            <button
                                                onClick={(e) => handleDeleteProject(project.id, e)}
                                                className="p-1.5 rounded-md text-[var(--muted)] hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>

                                        <div className="flex items-center gap-2 mb-3 flex-wrap">
                                            {project.building_type && (
                                                <span className="text-[10px] px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full font-medium">
                                                    🏢 {project.building_type}
                                                </span>
                                            )}
                                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${project.status === 'active'
                                                ? 'bg-green-50 text-green-600'
                                                : 'bg-slate-100 text-slate-500'
                                                }`}>
                                                {project.status === 'active' ? '進行中' : 'アーカイブ'}
                                            </span>
                                        </div>

                                        {/* Progress Bar */}
                                        <div className="mb-3">
                                            <div className="flex items-center justify-between text-[10px] text-[var(--muted)] mb-1">
                                                <span>
                                                    ✅ {project.progress.completed}件完了
                                                    {project.progress.in_progress > 0 && (
                                                        <span className="ml-2">🔄 {project.progress.in_progress}件検討中</span>
                                                    )}
                                                </span>
                                                <span className="font-semibold text-violet-600">{project.progress.percent}%</span>
                                            </div>
                                            <div className="w-full h-2 bg-[var(--background)] rounded-full overflow-hidden">
                                                <div
                                                    className="h-full rounded-full transition-all duration-500"
                                                    style={{
                                                        width: `${project.progress.percent}%`,
                                                        background: project.progress.percent === 100
                                                            ? 'linear-gradient(to right, #22c55e, #10b981)'
                                                            : 'linear-gradient(to right, #8b5cf6, #d946ef)',
                                                    }}
                                                />
                                            </div>
                                        </div>

                                        {/* Stats */}
                                        <div className="flex items-center gap-4 text-xs text-[var(--muted)]">
                                            <span className="flex items-center gap-1">
                                                <Target className="w-3 h-3" />
                                                {project.progress.completed}/{project.progress.total}
                                            </span>
                                            <span className="flex items-center gap-1">
                                                <Clock className="w-3 h-3" />
                                                {formatDate(project.updated_at)}
                                            </span>
                                            {project.delta_count > 0 && (
                                                <span className="text-violet-600">
                                                    📝 {project.delta_count} 変更
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ) : (
                    /* Templates Tab */
                    <div className="flex gap-6">
                        <div className="w-80 space-y-3 flex-shrink-0">
                            {templates.map(tmpl => (
                                <div
                                    key={tmpl.id}
                                    onClick={() => handlePreviewTemplate(tmpl.id)}
                                    className={`bg-[var(--card)] border rounded-xl p-4 cursor-pointer transition-all ${previewTemplate?.id === tmpl.id
                                        ? 'border-violet-500 shadow-lg shadow-violet-100'
                                        : 'border-[var(--border)] hover:border-violet-400'
                                        }`}
                                >
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className="text-lg">🏢</span>
                                        <h3 className="font-semibold text-sm">{tmpl.name}</h3>
                                    </div>
                                    <p className="text-xs text-[var(--muted)] mb-2">{tmpl.description}</p>
                                    <div className="flex items-center gap-3 text-xs text-[var(--muted)]">
                                        <span>{tmpl.node_count} ノード</span>
                                        <span>{tmpl.edge_count} 依存</span>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setShowCreateDialog(true);
                                        }}
                                        className="mt-3 w-full py-1.5 text-xs font-medium text-violet-600 border border-violet-300 rounded-lg hover:bg-violet-50 transition-colors"
                                    >
                                        このテンプレートでPJ作成
                                    </button>
                                </div>
                            ))}
                        </div>

                        {/* Template Preview */}
                        <div className="flex-1 bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden" style={{ minHeight: '500px' }}>
                            {previewTemplate ? (
                                <div className="h-full flex flex-col">
                                    <div className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between">
                                        <div>
                                            <h3 className="font-semibold text-sm">{previewTemplate.name}</h3>
                                            <p className="text-xs text-[var(--muted)]">テンプレートプレビュー（読み取り専用）</p>
                                        </div>
                                        <div className="flex items-center gap-1 px-2 py-1 bg-[var(--background)] rounded text-xs text-[var(--muted)]">
                                            <Eye className="w-3 h-3" />
                                            閲覧のみ
                                        </div>
                                    </div>
                                    <div className="flex-1">
                                        <ReactFlowProvider>
                                            <MindmapCanvas
                                                nodes={previewTemplate.nodes}
                                                edges={previewTemplate.edges}
                                                selectedNodeId={selectedNodeId}
                                                highlightedNodes={new Set()}
                                                highlightedEdges={new Set()}
                                                onNodeSelect={setSelectedNodeId}
                                                categoryColors={CATEGORY_COLORS}
                                                isEditMode={false}
                                                onNodeDragStop={() => { }}
                                            />
                                        </ReactFlowProvider>
                                    </div>
                                </div>
                            ) : (
                                <div className="h-full flex items-center justify-center text-[var(--muted)]">
                                    <div className="text-center">
                                        <Eye className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                        <p className="text-sm">テンプレートを選択してプレビュー</p>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </main>

            {/* Create Project Dialog */}
            {
                showCreateDialog && (
                    <CreateProjectDialog
                        templates={templates}
                        onClose={() => setShowCreateDialog(false)}
                        onCreate={handleCreateProject}
                    />
                )
            }

            {/* 課題→マインドマップ選択ダイアログ */}
            {showFromIssuesDialog && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowFromIssuesDialog(false)}>
                    <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
                        <h3 className="text-lg font-semibold text-gray-800 mb-1">課題プロジェクトを選択</h3>
                        <p className="text-xs text-gray-500 mb-4">課題因果グラフのデータをマインドマップとして表示します</p>
                        {issueProjects.length === 0 ? (
                            <div className="text-center py-6">
                                <p className="text-sm text-gray-400 mb-2">課題プロジェクトが見つかりません</p>
                                <Link href="/issues" className="text-sm text-blue-600 hover:underline">
                                    課題因果グラフで課題を追加
                                </Link>
                            </div>
                        ) : (
                            <div className="space-y-2 max-h-[300px] overflow-y-auto">
                                {issueProjects.map(({ name, count }) => (
                                    <button
                                        key={name}
                                        onClick={() => handleConvertFromIssues(name)}
                                        disabled={convertingIssues}
                                        className="w-full flex items-center gap-3 px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl hover:border-emerald-400 hover:bg-emerald-50 transition-colors text-left disabled:opacity-50"
                                    >
                                        <ClipboardList className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm font-medium text-gray-800 truncate">{name}</div>
                                            <div className="text-xs text-gray-400">{count}件の課題</div>
                                        </div>
                                        {convertingIssues && <Loader2 className="w-4 h-4 text-emerald-500 animate-spin" />}
                                    </button>
                                ))}
                            </div>
                        )}
                        <button
                            onClick={() => setShowFromIssuesDialog(false)}
                            className="w-full mt-4 text-sm text-gray-500 border border-gray-200 rounded-lg py-2 hover:bg-gray-50"
                        >
                            キャンセル
                        </button>
                    </div>
                </div>
            )}
        </div >
    );
}

// --- Create Project Dialog ---
function CreateProjectDialog({
    templates,
    onClose,
    onCreate,
}: {
    templates: TemplateListItem[];
    onClose: () => void;
    onCreate: (name: string, templateId: string, buildingType: string) => void;
}) {
    const [name, setName] = useState('');
    const [templateId, setTemplateId] = useState(templates[0]?.id || '');
    const [buildingType, setBuildingType] = useState('');

    const BUILDING_TYPES = ['事務所', '住宅', '商業施設', '工場・物流', '医療・福祉', '教育', 'その他'];

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-2xl shadow-2xl w-full max-w-md p-6">
                <h2 className="text-lg font-bold mb-4 text-[var(--foreground)]">
                    新規プロジェクト作成
                </h2>

                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-[var(--muted)] mb-1">プロジェクト名</label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="例：〇〇ビル設計"
                            className="w-full px-3 py-2 bg-[var(--background)] border border-[var(--border)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                            autoFocus
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-[var(--muted)] mb-1">建物用途（任意）</label>
                        <div className="relative">
                            <select
                                value={buildingType}
                                onChange={(e) => setBuildingType(e.target.value)}
                                className="w-full px-3 py-2 bg-[var(--background)] border border-[var(--border)] rounded-lg text-sm appearance-none pr-8 focus:outline-none focus:ring-2 focus:ring-violet-500"
                            >
                                <option value="">選択してください</option>
                                {BUILDING_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                            </select>
                            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted)] pointer-events-none" />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-[var(--muted)] mb-1">テンプレート</label>
                        <div className="relative">
                            <select
                                value={templateId}
                                onChange={(e) => setTemplateId(e.target.value)}
                                className="w-full px-3 py-2 bg-[var(--background)] border border-[var(--border)] rounded-lg text-sm appearance-none pr-8 focus:outline-none focus:ring-2 focus:ring-violet-500"
                            >
                                {templates.map(t => (
                                    <option key={t.id} value={t.id}>
                                        {t.name} ({t.node_count}ノード)
                                    </option>
                                ))}
                            </select>
                            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted)] pointer-events-none" />
                        </div>
                    </div>
                </div>

                <div className="flex gap-3 mt-6">
                    <button
                        onClick={onClose}
                        className="flex-1 py-2 text-sm font-medium text-[var(--muted)] border border-[var(--border)] rounded-lg hover:bg-[var(--background)] transition-colors"
                    >
                        キャンセル
                    </button>
                    <button
                        onClick={() => {
                            if (name.trim() && templateId) {
                                onCreate(name.trim(), templateId, buildingType);
                            }
                        }}
                        disabled={!name.trim() || !templateId}
                        className="flex-1 py-2 text-sm font-medium text-white bg-gradient-to-r from-violet-600 to-fuchsia-600 rounded-lg hover:from-violet-500 hover:to-fuchsia-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    >
                        作成
                    </button>
                </div>
            </div>
        </div>
    );
}
