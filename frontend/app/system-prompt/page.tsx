'use client';
import { authFetch } from '@/lib/api';
import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { ChevronLeft, Upload, RefreshCw, Save, FileText, CheckCircle, AlertCircle } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

interface Layer0Info {
    content: string;
    filename: string;
    filepath: string;
    file_exists: boolean;
    char_count: number;
}

type Status = { type: 'success' | 'error'; message: string } | null;

export default function SystemPromptPage() {
    const [info, setInfo] = useState<Layer0Info | null>(null);
    const [editContent, setEditContent] = useState('');
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [isReloading, setIsReloading] = useState(false);
    const [status, setStatus] = useState<Status>(null);
    const [isDirty, setIsDirty] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const showStatus = (type: 'success' | 'error', message: string) => {
        setStatus({ type, message });
        setTimeout(() => setStatus(null), 4000);
    };

    const fetchLayer0 = async () => {
        setIsLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/system/layer0`);
            if (!res.ok) throw new Error('取得失敗');
            const data: Layer0Info = await res.json();
            setInfo(data);
            setEditContent(data.content);
            setIsDirty(false);
        } catch (e) {
            showStatus('error', 'Layer 0の取得に失敗しました');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => { fetchLayer0(); }, []);

    const handleSave = async () => {
        if (!editContent.trim()) return;
        setIsSaving(true);
        try {
            const res = await authFetch(`${API_BASE}/api/system/layer0/text`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: editContent }),
            });
            if (!res.ok) throw new Error();
            const data = await res.json();
            showStatus('success', `保存しました（${data.char_count.toLocaleString()}文字）`);
            setIsDirty(false);
            await fetchLayer0();
        } catch {
            showStatus('error', '保存に失敗しました');
        } finally {
            setIsSaving(false);
        }
    };

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setIsUploading(true);
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await authFetch(`${API_BASE}/api/system/layer0/upload`, {
                method: 'POST',
                body: formData,
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'アップロード失敗');
            }
            const data = await res.json();
            showStatus('success', data.message);
            await fetchLayer0();
        } catch (e: any) {
            showStatus('error', e.message || 'アップロードに失敗しました');
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleReload = async () => {
        setIsReloading(true);
        try {
            const res = await authFetch(`${API_BASE}/api/system/layer0/reload`, { method: 'POST' });
            if (!res.ok) throw new Error();
            const data = await res.json();
            showStatus('success', data.message);
            await fetchLayer0();
        } catch {
            showStatus('error', '再読み込みに失敗しました');
        } finally {
            setIsReloading(false);
        }
    };

    const charCount = editContent.length;
    const charWarning = charCount > 3000;
    const charCaution = charCount > 1500;

    return (
        <div className="min-h-screen bg-slate-50 text-slate-900">
            {/* ヘッダー */}
            <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
                <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link href="/" className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                            <ChevronLeft className="w-5 h-5" />
                        </Link>
                        <div>
                            <h1 className="text-xl font-bold text-slate-800">Layer 0 管理</h1>
                            <p className="text-xs text-slate-400">
                                {info ? `${info.filepath}` : '読み込み中...'}
                            </p>
                        </div>
                    </div>
                    {/* ステータス表示 */}
                    {status && (
                        <div className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg ${status.type === 'success'
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-red-50 text-red-700'
                            }`}>
                            {status.type === 'success'
                                ? <CheckCircle className="w-4 h-4" />
                                : <AlertCircle className="w-4 h-4" />}
                            {status.message}
                        </div>
                    )}
                </div>
            </header>

            <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
                {/* アクションバー */}
                <div className="bg-white rounded-xl border border-slate-200 p-4">
                    <div className="flex flex-wrap items-center gap-3">
                        {/* ファイルアップロード */}
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".md,.txt"
                            className="hidden"
                            onChange={handleUpload}
                        />
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            disabled={isUploading}
                            className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-700 disabled:bg-violet-300 text-white text-sm font-medium rounded-lg transition-colors"
                        >
                            <Upload className="w-4 h-4" />
                            {isUploading ? 'アップロード中...' : 'MDファイルを入れ替え'}
                        </button>

                        {/* 再読み込み */}
                        <button
                            onClick={handleReload}
                            disabled={isReloading}
                            className="flex items-center gap-2 px-4 py-2 border border-slate-200 hover:bg-slate-50 disabled:opacity-50 text-slate-700 text-sm font-medium rounded-lg transition-colors"
                        >
                            <RefreshCw className={`w-4 h-4 ${isReloading ? 'animate-spin' : ''}`} />
                            再読み込み
                        </button>

                        {/* 文字数インジケーター */}
                        <div className={`ml-auto text-sm font-mono px-3 py-1.5 rounded-lg ${charWarning
                                ? 'bg-red-50 text-red-600'
                                : charCaution
                                    ? 'bg-amber-50 text-amber-600'
                                    : 'bg-slate-100 text-slate-500'
                            }`}>
                            {charCount.toLocaleString()} 文字
                            {charCaution && !charWarning && ' ⚠ 1,500超'}
                            {charWarning && ' ⛔ 3,000超'}
                        </div>
                    </div>
                    {charWarning && (
                        <p className="mt-2 text-xs text-red-600">
                            3,000文字を超えるとLLMが一部指示を選択的に無視する可能性があります。
                        </p>
                    )}
                    {charCaution && !charWarning && (
                        <p className="mt-2 text-xs text-amber-600">
                            1,500文字が推奨上限です。優先度の低い記述は削減を検討してください。
                        </p>
                    )}
                </div>

                {/* エディタ */}
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
                        <div className="flex items-center gap-2 text-sm text-slate-500">
                            <FileText className="w-4 h-4" />
                            <span>{info?.filename || 'layer0_principles.md'}</span>
                            {isDirty && <span className="text-amber-500 text-xs">● 未保存</span>}
                        </div>
                        <button
                            onClick={handleSave}
                            disabled={isSaving || !isDirty}
                            className="flex items-center gap-2 px-4 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:bg-slate-300 text-white text-sm font-medium rounded-lg transition-colors"
                        >
                            <Save className="w-3.5 h-3.5" />
                            {isSaving ? '保存中...' : '保存して適用'}
                        </button>
                    </div>
                    {isLoading ? (
                        <div className="h-96 flex items-center justify-center text-slate-400">
                            読み込み中...
                        </div>
                    ) : (
                        <textarea
                            value={editContent}
                            onChange={e => {
                                setEditContent(e.target.value);
                                setIsDirty(true);
                            }}
                            className="w-full h-96 p-4 font-mono text-sm text-slate-800 bg-white resize-none focus:outline-none"
                            placeholder="Layer 0プロンプトをここに入力..."
                            spellCheck={false}
                        />
                    )}
                </div>

                {/* 現在の適用状態 */}
                {info && (
                    <div className="bg-slate-100 rounded-xl p-4 text-xs text-slate-500 space-y-1">
                        <div>現在のキャッシュ: <span className="font-mono">{info.char_count.toLocaleString()} 文字</span></div>
                        <div>ファイル状態: {info.file_exists ? '✅ 存在する' : '❌ ファイルなし（フォールバック使用中）'}</div>
                        <div className="text-slate-400">※「保存して適用」または「MDファイルを入れ替え」後、次のチャットから新しい内容が使われます</div>
                    </div>
                )}
            </main>
        </div>
    );
}
