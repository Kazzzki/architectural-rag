'use client';

import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { ReactFlowProvider } from 'reactflow';
import MindmapCanvas from '../../components/mindmap/MindmapCanvas';
import { FolderOpen, ArrowLeft, RefreshCw, AlertCircle, FileText, Brain, Sparkles, Upload, X, Download, BookOpen, Check, Trash2, Settings, CheckCircle } from 'lucide-react';
import Link from 'next/link';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const CATEGORY_COLORS: Record<string, string> = {
    'Folder': '#fbbf24',
    'File': '#94a3b8',
    '設計': '#3b82f6',
    '管理': '#6b7280',
    '技術': '#ef4444',
    '分析': '#8b5cf6',
    'データ': '#22c55e',
    '文書': '#f59e0b',
    '構造': '#ef4444',
    '意匠': '#3b82f6',
    '設備': '#22c55e',
};

interface ProcessNode {
    id: string;
    label: string;
    description: string;
    phase: string;
    category: string;
    checklist: string[];
    deliverables: string[];
    key_stakeholders: string[];
    position: { x: number; y: number };
    status: string;
}

interface EdgeData {
    id: string;
    source: string;
    target: string;
    type: string;
    reason: string;
}

type ScanMode = 'upload' | 'directory' | 'analyze';

const DEFAULT_PATH = '/Users/kkk/Dropbox (個人用)/My Mac (kkkのMac mini)/Downloads';

function SettingsModal({ onClose, onSave }: { onClose: () => void; onSave?: (hasKey: boolean) => void }) {
    const [tab, setTab] = useState<'api' | 'rules'>('api');
    const [apiKey, setApiKey] = useState('');
    const [maskedKey, setMaskedKey] = useState('');
    const [hasKey, setHasKey] = useState(false);
    const [selectedModel, setSelectedModel] = useState('gemini-3.0-flash-preview');
    const [availableModels, setAvailableModels] = useState<string[]>([]);
    const [loading, setLoading] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
    const [rules, setRules] = useState<string[]>([]);
    const [newRule, setNewRule] = useState('');
    const [editingIdx, setEditingIdx] = useState<number | null>(null);
    const [editingText, setEditingText] = useState('');
    const [rulesLoading, setRulesLoading] = useState(false);
    const [rulesSaving, setRulesSaving] = useState(false);

    useEffect(() => {
        fetch(`${API_BASE}/api/mindmap/settings`)
            .then(res => res.json())
            .then(data => {
                setMaskedKey(data.gemini_api_key_masked || '');
                setHasKey(data.has_api_key || false);
                setSelectedModel(data.analysis_model || 'gemini-3.0-flash-preview');
                setAvailableModels(data.available_models || []);
            }).catch(console.error);
        setRulesLoading(true);
        fetch(`${API_BASE}/api/mindmap/fs/rules`)
            .then(res => res.json())
            .then(data => setRules(data.rules || []))
            .catch(console.error)
            .finally(() => setRulesLoading(false));
    }, []);

    const handleSaveApi = async () => {
        setLoading(true);
        try {
            const body: Record<string, string> = { analysis_model: selectedModel };
            if (apiKey) body.gemini_api_key = apiKey;
            const res = await fetch(`${API_BASE}/api/mindmap/settings`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error('Failed');
            const data = await res.json();
            setMaskedKey(data.settings?.gemini_api_key_masked || '');
            setHasKey(data.settings?.has_api_key || false);
            setApiKey('');
            setTestResult({ success: true, message: '設定を保存しました' });
            if (onSave) onSave(data.settings?.has_api_key || false);
        } catch { setTestResult({ success: false, message: '保存に失敗しました' }); }
        finally { setLoading(false); }
    };

    const saveRules = async (updated: string[]) => {
        setRulesSaving(true);
        try {
            const res = await fetch(`${API_BASE}/api/mindmap/fs/rules`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rules: updated }),
            });
            if (!res.ok) throw new Error('Failed');
            const data = await res.json();
            setRules(data.rules || []);
        } catch (e) { console.error('Rule save error:', e); }
        finally { setRulesSaving(false); }
    };

    const addRule = () => { if (!newRule.trim()) return; saveRules([...rules, newRule.trim()]); setNewRule(''); };
    const deleteRule = (i: number) => saveRules(rules.filter((_, j) => j !== i));
    const startEdit = (i: number) => { setEditingIdx(i); setEditingText(rules[i]); };
    const saveEdit = () => { if (editingIdx === null || !editingText.trim()) return; saveRules(rules.map((r, i) => i === editingIdx ? editingText.trim() : r)); setEditingIdx(null); };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full overflow-hidden max-h-[85vh] flex flex-col">
                <div className="flex items-center justify-between p-4 border-b border-gray-100 shrink-0">
                    <h3 className="font-bold flex items-center gap-2">
                        <Settings className="w-5 h-5 text-slate-500" />
                        設定
                    </h3>
                    <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded-full">
                        <X className="w-5 h-5 text-slate-400" />
                    </button>
                </div>
                <div className="flex border-b border-gray-100 shrink-0">
                    <button onClick={() => setTab('api')} className={`flex-1 py-2.5 text-sm font-medium transition-colors ${tab === 'api' ? 'text-violet-700 border-b-2 border-violet-600 bg-violet-50/50' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'}`}>
                        🔑 API設定
                    </button>
                    <button onClick={() => setTab('rules')} className={`flex-1 py-2.5 text-sm font-medium transition-colors ${tab === 'rules' ? 'text-violet-700 border-b-2 border-violet-600 bg-violet-50/50' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'}`}>
                        📋 ルールブック ({rules.length})
                    </button>
                </div>
                <div className="overflow-y-auto flex-1">
                    {tab === 'api' ? (
                        <div className="p-6 space-y-5">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Gemini API Key</label>
                                {hasKey && !apiKey && (
                                    <div className="flex items-center gap-2 mb-2 px-3 py-2 bg-emerald-50 border border-emerald-200 rounded-lg">
                                        <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
                                        <span className="text-xs text-emerald-700 font-mono">{maskedKey}</span>
                                    </div>
                                )}
                                <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                                    placeholder={hasKey ? "新しいキーで上書き..." : "AIza..."}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 text-sm font-mono" />
                                <p className="text-xs text-slate-500 mt-1">
                                    <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener" className="text-violet-600 hover:underline">Google AI Studio</a>で取得したAPIキーを入力してください。
                                </p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">分析モデル</label>
                                <select value={selectedModel} onChange={e => setSelectedModel(e.target.value)}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 text-sm bg-white">
                                    {availableModels.map(m => (<option key={m} value={m}>{m}</option>))}
                                </select>
                            </div>
                            {testResult && (
                                <div className={`p-3 rounded-lg text-sm flex items-start gap-2 ${testResult.success ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
                                    {testResult.success ? <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" /> : <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />}
                                    <span>{testResult.message}</span>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="p-6 space-y-4">
                            <p className="text-xs text-slate-500">
                                AIがテキストをマインドマップに変換する際のルールを定義します。ルールは分析時にプロンプトに追加されます。
                            </p>
                            {rulesLoading ? (
                                <div className="text-center py-8 text-slate-400">
                                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />読み込み中...
                                </div>
                            ) : rules.length === 0 ? (
                                <div className="text-center py-8 text-slate-400">
                                    <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-40" />
                                    <p className="text-sm">ルールが未設定です</p>
                                    <p className="text-xs mt-1">下のフォームからルールを追加してください</p>
                                </div>
                            ) : (
                                <div className="space-y-2 max-h-[40vh] overflow-y-auto">
                                    {rules.map((rule, idx) => (
                                        <div key={idx} className="group relative bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm">
                                            {editingIdx === idx ? (
                                                <div className="space-y-2">
                                                    <textarea value={editingText} onChange={e => setEditingText(e.target.value)}
                                                        className="w-full px-2 py-1.5 border border-violet-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 resize-none"
                                                        rows={3} autoFocus />
                                                    <div className="flex justify-end gap-1.5">
                                                        <button onClick={() => { setEditingIdx(null); setEditingText(''); }} className="px-2 py-1 text-xs text-slate-500 hover:text-slate-700">キャンセル</button>
                                                        <button onClick={saveEdit} className="px-2 py-1 text-xs bg-violet-600 text-white rounded hover:bg-violet-700">保存</button>
                                                    </div>
                                                </div>
                                            ) : (
                                                <>
                                                    <div className="flex items-start gap-2 pr-14">
                                                        <span className="text-slate-400 text-xs font-mono shrink-0 mt-0.5">{idx + 1}.</span>
                                                        <span className="text-slate-700 leading-relaxed">{rule}</span>
                                                    </div>
                                                    <div className="absolute top-2 right-2 hidden group-hover:flex items-center gap-1">
                                                        <button onClick={() => startEdit(idx)} className="p-1 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded" title="編集">✏️</button>
                                                        <button onClick={() => deleteRule(idx)} className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded" title="削除">
                                                            <Trash2 className="w-3.5 h-3.5" />
                                                        </button>
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                            <div className="border-t border-slate-100 pt-4">
                                <label className="block text-xs font-medium text-slate-600 mb-1.5">新しいルールを追加</label>
                                <div className="flex gap-2">
                                    <textarea value={newRule} onChange={e => setNewRule(e.target.value)}
                                        placeholder="例: ノードのラベルは日本語で記述し、20文字以内にする"
                                        className="flex-1 px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 text-sm resize-none" rows={2}
                                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); addRule(); } }} />
                                    <button onClick={addRule} disabled={!newRule.trim() || rulesSaving}
                                        className="self-end px-3 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-sm font-medium disabled:opacity-50 shrink-0">追加</button>
                                </div>
                            </div>
                            {rulesSaving && (
                                <div className="text-center text-xs text-violet-600 flex items-center justify-center gap-1">
                                    <RefreshCw className="w-3 h-3 animate-spin" /> 保存中...
                                </div>
                            )}
                        </div>
                    )}
                </div>
                {tab === 'api' && (
                    <div className="p-4 bg-slate-50 border-t border-slate-100 flex justify-end shrink-0">
                        <button onClick={handleSaveApi} disabled={loading || (!apiKey && !selectedModel)}
                            className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-medium text-sm transition-colors flex items-center gap-2 disabled:opacity-50">
                            {loading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                            保存
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

export default function LocalMindmapPage() {
    const [path, setPath] = useState(DEFAULT_PATH);
    const [nodes, setNodes] = useState<ProcessNode[]>([]);
    const [edges, setEdges] = useState<EdgeData[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [mode, setMode] = useState<ScanMode>('upload');
    const [analysisTitle, setAnalysisTitle] = useState<string | null>(null);
    const [sourceFiles, setSourceFiles] = useState<string[]>([]);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

    // Upload state
    const [uploadFiles, setUploadFiles] = useState<File[]>([]);
    const [isDragOver, setIsDragOver] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Rule learning state
    const [originalNodes, setOriginalNodes] = useState<ProcessNode[]>([]);
    const [originalEdges, setOriginalEdges] = useState<EdgeData[]>([]);
    const [hasEdits, setHasEdits] = useState(false);
    const [learningRules, setLearningRules] = useState(false);
    const [ruleMessage, setRuleMessage] = useState<string | null>(null);
    const [exporting, setExporting] = useState(false);
    const [showSettings, setShowSettings] = useState(false);
    const [hasApiKey, setHasApiKey] = useState<boolean | null>(null);

    // Check API key status on mount
    useEffect(() => {
        fetch(`${API_BASE}/api/mindmap/settings`)
            .then(res => res.json())
            .then(data => {
                setHasApiKey(data.has_api_key || false);
                if (!data.has_api_key) {
                    setShowSettings(true); // Auto-open settings if no key
                }
            })
            .catch(() => setHasApiKey(false));
    }, []);

    // Stable references to avoid infinite re-render loops
    const emptySet = useMemo(() => new Set<string>(), []);

    // Track node position changes
    // Track node position changes
    const handleNodeDragStop = useCallback((nodeId: string, x: number, y: number) => {
        setNodes(prev => prev.map(n =>
            n.id === nodeId ? { ...n, position: { x, y } } : n
        ));
        setHasEdits(true);
    }, []);

    // Track label changes
    const handleNodeLabelChange = useCallback((nodeId: string, newLabel: string) => {
        setNodes(prev => prev.map(n =>
            n.id === nodeId ? { ...n, label: newLabel } : n
        ));
        setHasEdits(true);
    }, []);

    // File drop handlers
    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(false);
        const files = Array.from(e.dataTransfer.files);
        setUploadFiles(prev => [...prev, ...files]);
    }, []);

    const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            const files = Array.from(e.target.files);
            setUploadFiles(prev => [...prev, ...files]);
        }
        if (fileInputRef.current) fileInputRef.current.value = '';
    }, []);

    const removeFile = useCallback((index: number) => {
        setUploadFiles(prev => prev.filter((_, i) => i !== index));
    }, []);

    const clearFiles = useCallback(() => {
        setUploadFiles([]);
    }, []);

    // Apply analysis result and save original for comparison
    const applyAnalysisResult = (data: any) => {
        const newNodes = data.nodes || [];
        const newEdges = data.edges || [];
        setNodes(newNodes);
        setEdges(newEdges);
        setOriginalNodes(JSON.parse(JSON.stringify(newNodes)));
        setOriginalEdges(JSON.parse(JSON.stringify(newEdges)));
        setAnalysisTitle(data.title);
        setSourceFiles(data.source_files || []);
        setHasEdits(false);
        setRuleMessage(null);
    };

    // Upload and analyze
    const handleUploadAnalyze = async () => {
        if (uploadFiles.length === 0) return;
        setLoading(true);
        setError(null);
        try {
            const formData = new FormData();
            uploadFiles.forEach(file => formData.append('files', file));
            const res = await fetch(`${API_BASE}/api/mindmap/fs/upload-analyze`, {
                method: 'POST',
                body: formData,
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Upload analysis failed');
            }
            const data = await res.json();
            applyAnalysisResult(data);
        } catch (err: any) {
            setError(err.message || 'Failed to analyze');
        } finally {
            setLoading(false);
        }
    };

    const handleScan = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!path.trim()) return;
        setLoading(true);
        setError(null);
        try {
            if (mode === 'directory') {
                const res = await fetch(`${API_BASE}/api/mindmap/fs/scan?path=${encodeURIComponent(path)}`);
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Path not found or access denied');
                }
                const data = await res.json();
                const processNodes: ProcessNode[] = (data.nodes || []).map((n: any) => ({
                    id: n.id, label: n.data?.label || n.id, description: '',
                    phase: n.data?.is_dir ? 'フォルダ' : 'ファイル',
                    category: n.data?.is_dir ? 'Folder' : 'File',
                    checklist: [], deliverables: [], key_stakeholders: [],
                    position: n.position || { x: 0, y: 0 }, status: '未着手',
                }));
                const processEdges: EdgeData[] = (data.edges || []).map((e: any) => ({
                    id: e.id, source: e.source, target: e.target, type: e.type || 'hard', reason: '',
                }));
                setNodes(processNodes);
                setEdges(processEdges);
                setOriginalNodes(JSON.parse(JSON.stringify(processNodes)));
                setOriginalEdges(JSON.parse(JSON.stringify(processEdges)));
                setHasEdits(false);
                setRuleMessage(null);
            } else if (mode === 'analyze') {
                const res = await fetch(`${API_BASE}/api/mindmap/fs/analyze`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: path, max_files: 20 }),
                });
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Analysis failed');
                }
                const data = await res.json();
                applyAnalysisResult(data);
            }
        } catch (err: any) {
            setError(err.message || 'Failed to process');
        } finally {
            setLoading(false);
        }
    };

    // Rule learning: send diff to backend
    const handleLearnRules = async () => {
        if (!hasEdits || originalNodes.length === 0) return;
        setLearningRules(true);
        setRuleMessage(null);
        try {
            const res = await fetch(`${API_BASE}/api/mindmap/fs/learn-rules`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    original_nodes: originalNodes,
                    original_edges: originalEdges,
                    edited_nodes: nodes,
                    edited_edges: edges,
                }),
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Rule learning failed');
            }
            const data = await res.json();
            setRuleMessage(`${data.new_rules.length}件のルールを学習しました（合計: ${data.total_rules}件）`);
            // Update originals to current state
            setOriginalNodes(JSON.parse(JSON.stringify(nodes)));
            setOriginalEdges(JSON.parse(JSON.stringify(edges)));
            setHasEdits(false);
        } catch (err: any) {
            setError(err.message || 'Rule learning failed');
        } finally {
            setLearningRules(false);
        }
    };

    // Export mindmap as Markdown
    const handleExportMd = async () => {
        if (nodes.length === 0) return;
        setExporting(true);
        try {
            const res = await fetch(`${API_BASE}/api/mindmap/fs/export-md`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: analysisTitle || 'マインドマップ',
                    nodes,
                    edges,
                }),
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Export failed');
            }
            const data = await res.json();
            // Trigger download
            const blob = new Blob([data.markdown], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${(data.title || 'mindmap').replace(/[/\\?%*:|"<>]/g, '_')}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err: any) {
            setError(err.message || 'Export failed');
        } finally {
            setExporting(false);
        }
    };

    // Save to Project
    const [showSaveModal, setShowSaveModal] = useState(false);
    const [projectName, setProjectName] = useState('');
    const [savingProject, setSavingProject] = useState(false);

    const handleSaveToProject = async () => {
        if (!projectName.trim()) return;
        setSavingProject(true);
        try {
            const body = {
                name: projectName,
                nodes: nodes,
                edges: edges,
                template_id: "blank"
            };
            const res = await fetch(`${API_BASE}/api/mindmap/projects/import`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Project save failed');
            }

            const data = await res.json();
            // Redirect to the new project
            window.location.href = `/mindmap/projects/${data.id}`;

        } catch (err: any) {
            setError(err.message || 'Failed to save project');
            setSavingProject(false);
            setShowSaveModal(false);
        }
    };

    return (
        <div className="h-screen flex flex-col bg-[var(--background)]">
            {showSettings && <SettingsModal onClose={() => setShowSettings(false)} onSave={(hasKey) => setHasApiKey(hasKey)} />}

            {showSaveModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white rounded-xl shadow-2xl max-w-sm w-full p-6">
                        <h3 className="font-bold text-lg mb-4">プロジェクトとして保存</h3>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">プロジェクト名</label>
                                <input
                                    type="text"
                                    value={projectName}
                                    onChange={e => setProjectName(e.target.value)}
                                    placeholder="例: 文書分析プロジェクト"
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500"
                                    autoFocus
                                />
                            </div>
                            <div className="flex justify-end gap-2 pt-2">
                                <button
                                    onClick={() => setShowSaveModal(false)}
                                    className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg text-sm font-medium"
                                >
                                    キャンセル
                                </button>
                                <button
                                    onClick={handleSaveToProject}
                                    disabled={!projectName.trim() || savingProject}
                                    className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-sm font-medium flex items-center gap-2 disabled:opacity-50"
                                >
                                    {savingProject && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                                    作成して移動
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            <header className="border-b border-[var(--border)] bg-white/80 backdrop-blur-sm px-6 py-3 z-10">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-4">
                        <Link href="/mindmap" className="p-2 hover:bg-slate-100 rounded-full text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                            <ArrowLeft className="w-5 h-5" />
                        </Link>
                        <div className="flex items-center gap-2">
                            {mode === 'upload' ? (
                                <Upload className="w-5 h-5 text-violet-600" />
                            ) : mode === 'analyze' ? (
                                <Brain className="w-5 h-5 text-violet-600" />
                            ) : (
                                <FolderOpen className="w-5 h-5 text-amber-600" />
                            )}
                            <h1 className="font-bold text-[var(--foreground)]">
                                {mode === 'upload' ? 'ファイルアップロード分析' : mode === 'analyze' ? 'パス指定AI分析' : 'ディレクトリスキャン'}
                            </h1>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => setShowSettings(true)}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all border ${hasApiKey === false
                                ? 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100 animate-pulse'
                                : hasApiKey
                                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                                    : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                                }`}
                        >
                            <Settings className="w-4 h-4" />
                            {hasApiKey === false ? 'APIキー未設定' : 'API設定'}
                            {hasApiKey && <CheckCircle className="w-3.5 h-3.5" />}
                        </button>

                        {/* Action buttons */}
                        {nodes.length > 0 && (
                            <div className="flex items-center gap-1.5 border-l border-slate-200 pl-3 ml-1">
                                <button
                                    onClick={handleLearnRules}
                                    disabled={!hasEdits || learningRules}
                                    title={hasEdits ? 'AIの分析ルールを学習' : '編集してからルール学習できます'}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${hasEdits
                                        ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm'
                                        : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                                        }`}
                                >
                                    {learningRules ? (
                                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                        <BookOpen className="w-3.5 h-3.5" />
                                    )}
                                    {learningRules ? '学習中...' : 'ルール学習'}
                                </button>
                                <button
                                    onClick={handleExportMd}
                                    disabled={exporting}
                                    title="Markdownファイルとしてエクスポート"
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-all disabled:opacity-50"
                                >
                                    {exporting ? (
                                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                        <Download className="w-3.5 h-3.5" />
                                    )}
                                    MD出力
                                </button>
                                <button
                                    onClick={() => {
                                        setProjectName(analysisTitle || "分析結果マインドマップ");
                                        setShowSaveModal(true);
                                    }}
                                    title="プロジェクトとして保存"
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-all"
                                >
                                    <FolderOpen className="w-3.5 h-3.5" />
                                    保存
                                </button>
                            </div>
                        )}

                        {/* Mode Switch */}
                        <div className="flex items-center bg-slate-100 rounded-lg p-1 gap-0.5">
                            <button
                                onClick={() => setMode('upload')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${mode === 'upload'
                                    ? 'bg-white text-violet-700 shadow-sm'
                                    : 'text-slate-500 hover:text-slate-700'
                                    }`}
                            >
                                <Upload className="w-3.5 h-3.5" />
                                アップロード
                            </button>
                            <button
                                onClick={() => setMode('analyze')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${mode === 'analyze'
                                    ? 'bg-white text-violet-700 shadow-sm'
                                    : 'text-slate-500 hover:text-slate-700'
                                    }`}
                            >
                                <Sparkles className="w-3.5 h-3.5" />
                                パス指定
                            </button>
                            <button
                                onClick={() => setMode('directory')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${mode === 'directory'
                                    ? 'bg-white text-amber-700 shadow-sm'
                                    : 'text-slate-500 hover:text-slate-700'
                                    }`}
                            >
                                <FolderOpen className="w-3.5 h-3.5" />
                                ディレクトリ
                            </button>
                        </div>
                    </div>
                </div>

                {/* Upload mode: drag & drop area */}
                {mode === 'upload' && (
                    <div className="flex gap-2 items-start">
                        <div
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                            className={`flex-1 border-2 border-dashed rounded-lg px-4 py-3 cursor-pointer transition-all ${isDragOver
                                ? 'border-violet-500 bg-violet-50'
                                : 'border-slate-300 hover:border-violet-400 hover:bg-violet-50/50'
                                }`}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                multiple
                                className="hidden"
                                onChange={handleFileSelect}
                                accept=".txt,.md,.csv,.log,.json,.yaml,.yml,.xml,.html,.htm,.py,.js,.ts,.tsx,.jsx,.css,.sql,.sh,.bat,.ini,.cfg,.conf,.env,.rst,.tex"
                            />
                            {uploadFiles.length === 0 ? (
                                <div className="text-center text-sm text-slate-500">
                                    <Upload className="w-5 h-5 mx-auto mb-1 text-slate-400" />
                                    <span>ファイルをドラッグ&ドロップ、またはクリックして選択</span>
                                    <p className="text-xs text-slate-400 mt-0.5">対応: .txt, .md, .csv, .json, .yaml, .py, .js 等</p>
                                </div>
                            ) : (
                                <div className="flex flex-wrap gap-1.5">
                                    {uploadFiles.map((file, i) => (
                                        <span
                                            key={`${file.name}-${i}`}
                                            className="inline-flex items-center gap-1 bg-violet-100 text-violet-700 text-xs px-2 py-1 rounded-md"
                                        >
                                            <FileText className="w-3 h-3" />
                                            {file.name}
                                            <button
                                                onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                                                className="hover:bg-violet-200 rounded-full p-0.5"
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </span>
                                    ))}
                                    <button
                                        onClick={(e) => { e.stopPropagation(); clearFiles(); }}
                                        className="text-xs text-slate-400 hover:text-red-500 px-1"
                                    >
                                        全削除
                                    </button>
                                </div>
                            )}
                        </div>
                        <button
                            onClick={handleUploadAnalyze}
                            disabled={loading || uploadFiles.length === 0}
                            className="px-6 py-3 bg-violet-600 hover:bg-violet-700 text-white rounded-lg flex items-center gap-2 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                        >
                            {loading ? (
                                <RefreshCw className="w-4 h-4 animate-spin" />
                            ) : (
                                <Sparkles className="w-4 h-4" />
                            )}
                            {loading ? 'AI分析中...' : 'AI分析'}
                        </button>
                    </div>
                )}

                {/* Path input mode */}
                {mode !== 'upload' && (
                    <form onSubmit={handleScan} className="flex gap-2">
                        <input
                            type="text"
                            value={path}
                            onChange={e => setPath(e.target.value)}
                            placeholder={mode === 'analyze' ? 'テキストファイルのパスまたはフォルダパス...' : '/Users/username/Documents...'}
                            className="flex-1 px-4 py-2 rounded-lg border border-[var(--border)] bg-white focus:outline-none focus:ring-2 focus:ring-violet-500 shadow-sm text-sm"
                        />
                        <button
                            type="submit"
                            disabled={loading}
                            className={`px-6 py-2 text-white rounded-lg flex items-center gap-2 font-medium transition-colors disabled:opacity-70 ${mode === 'analyze' ? 'bg-violet-600 hover:bg-violet-700' : 'bg-amber-600 hover:bg-amber-700'}`}
                        >
                            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : mode === 'analyze' ? <Sparkles className="w-4 h-4" /> : <RefreshCw className="w-4 h-4" />}
                            {loading ? (mode === 'analyze' ? 'AI分析中...' : 'スキャン中...') : (mode === 'analyze' ? 'AI分析' : 'スキャン')}
                        </button>
                    </form>
                )}
            </header>

            <div className="flex-1 relative bg-[var(--canvas-bg)]">
                {error && (
                    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 max-w-lg">
                        <AlertCircle className="w-5 h-5 flex-shrink-0" />
                        <span className="text-sm">{error}</span>
                        <button onClick={() => setError(null)} className="ml-2 hover:bg-red-100 rounded p-0.5">
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                )}

                {/* Rule learning success message */}
                {ruleMessage && (
                    <div className="absolute top-4 right-4 z-20 bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 max-w-sm animate-in">
                        <Check className="w-5 h-5 flex-shrink-0" />
                        <span className="text-sm">{ruleMessage}</span>
                        <button onClick={() => setRuleMessage(null)} className="ml-2 hover:bg-emerald-100 rounded p-0.5">
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                )}

                {/* Analysis Info Banner */}
                {analysisTitle && (
                    <div className="absolute top-4 left-4 z-20 bg-white/95 backdrop-blur-sm border border-violet-200 rounded-xl shadow-lg px-4 py-3 max-w-sm">
                        <div className="flex items-center gap-2 mb-1">
                            <Brain className="w-4 h-4 text-violet-600" />
                            <span className="font-bold text-sm text-[var(--foreground)]">{analysisTitle}</span>
                            {hasEdits && (
                                <span className="text-[9px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">編集済み</span>
                            )}
                        </div>
                        <div className="text-[10px] text-[var(--muted)]">
                            {sourceFiles.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-1">
                                    {sourceFiles.slice(0, 5).map(f => (
                                        <span key={f} className="bg-violet-50 text-violet-600 px-1.5 py-0.5 rounded">
                                            <FileText className="w-2.5 h-2.5 inline mr-0.5" />
                                            {f}
                                        </span>
                                    ))}
                                    {sourceFiles.length > 5 && (
                                        <span className="text-[var(--muted)]">+{sourceFiles.length - 5} more</span>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {nodes.length === 0 && !loading && !error && (
                    <div className="absolute inset-0 flex items-center justify-center text-[var(--muted)] pointer-events-none">
                        <div className="text-center">
                            {mode === 'upload' ? (
                                <>
                                    <Upload className="w-16 h-16 mx-auto mb-4 opacity-20" />
                                    <p className="text-lg font-medium">ファイルをアップロードしてAI分析を開始</p>
                                    <p className="text-sm mt-2 opacity-60">対応形式: .txt, .md, .csv, .json, .yaml, .py 等</p>
                                    <p className="text-xs mt-4 opacity-40">分析後にノードを編集 → ルール学習で精度向上</p>
                                </>
                            ) : mode === 'analyze' ? (
                                <>
                                    <Brain className="w-16 h-16 mx-auto mb-4 opacity-20" />
                                    <p className="text-lg font-medium">テキストファイルのパスを入力してAI分析を開始</p>
                                    <p className="text-sm mt-2 opacity-60">対応形式: .txt, .md, .csv, .json, .yaml 等</p>
                                </>
                            ) : (
                                <>
                                    <FolderOpen className="w-16 h-16 mx-auto mb-4 opacity-20" />
                                    <p className="text-lg font-medium">パスを入力してスキャンを開始</p>
                                </>
                            )}
                        </div>
                    </div>
                )}

                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center z-30 bg-white/50 backdrop-blur-sm">
                        <div className="bg-white rounded-2xl shadow-2xl border border-violet-100 p-8 text-center">
                            <div className="relative mx-auto w-16 h-16 mb-4">
                                <div className="absolute inset-0 rounded-full border-4 border-violet-100"></div>
                                <div className="absolute inset-0 rounded-full border-4 border-t-violet-600 animate-spin"></div>
                                <Sparkles className="absolute inset-0 m-auto w-6 h-6 text-violet-600" />
                            </div>
                            <p className="font-bold text-[var(--foreground)]">
                                {mode === 'directory' ? 'スキャン中...' : 'Gemini AIで分析中...'}
                            </p>
                            <p className="text-sm text-[var(--muted)] mt-1">しばらくお待ちください</p>
                        </div>
                    </div>
                )}

                <ReactFlowProvider>
                    <MindmapCanvas
                        nodes={nodes}
                        edges={edges}
                        selectedNodeId={selectedNodeId}
                        highlightedNodes={emptySet}
                        highlightedEdges={emptySet}
                        onNodeSelect={setSelectedNodeId}
                        categoryColors={CATEGORY_COLORS}
                        isEditMode={true}
                        onNodeDragStop={handleNodeDragStop}
                        onNodeLabelChange={handleNodeLabelChange}
                    />
                </ReactFlowProvider>
            </div>
        </div>
    );
}
