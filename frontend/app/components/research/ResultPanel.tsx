import React, { useState } from 'react';
import { ParsedResearchResponse, KnowledgeItem, PipelineNode } from '../../types/research';
import { Download, Check, Copy, AlertCircle, Database, FileText, Search, RefreshCw } from 'lucide-react';
import { authFetch } from '../../../lib/api';

const API_BASE = "";

interface ResultPanelProps {
    parsedData: ParsedResearchResponse | null;
    node: PipelineNode | null;
    isGenerating: boolean;
    rawStreamText: string;
}

export default function ResultPanel({ parsedData, node, isGenerating, rawStreamText }: ResultPanelProps) {
    const [activeTab, setActiveTab] = useState<'gaps' | 'instructions' | 'rag'>('gaps');
    const [activeToolIndex, setActiveToolIndex] = useState(0);
    const [copiedStates, setCopiedStates] = useState<{ [key: string]: boolean }>({});
    const [isInjecting, setIsInjecting] = useState(false);
    const [injectSuccess, setInjectSuccess] = useState<string | null>(null);
    const [injectError, setInjectError] = useState<string | null>(null);

    const handleCopy = (text: string, id: string) => {
        navigator.clipboard.writeText(text);
        setCopiedStates({ ...copiedStates, [id]: true });
        setTimeout(() => setCopiedStates({ ...copiedStates, [id]: false }), 2000);
    };

    const handleInject = async () => {
        if (!node || !parsedData?.knowledgeItems.length) return;

        setIsInjecting(true);
        setInjectError(null);
        setInjectSuccess(null);

        try {
            const itemsToInject: KnowledgeItem[] = parsedData.knowledgeItems.map((item, idx) => ({
                id: `ki_${node.id}_${Date.now()}_${idx}`,
                title: item.title,
                content: item.content,
                tags: item.tags,
                search_category: "rag_retrieval",
                doc_type: node.default_doc_type || "spec"
            }));

            const payload = {
                node_id: node.id,
                node_label: node.label,
                items: itemsToInject
            };

            const response = await authFetch(`${API_BASE}/api/research/inject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to inject items');
            }

            const data = await response.json();
            setInjectSuccess(`${data.injected}件の知識アイテムをChromaDBに投入しました！`);
        } catch (error: any) {
            console.error("Inject error:", error);
            setInjectError(error.message || "投入中にエラーが発生しました");
        } finally {
            setIsInjecting(false);
        }
    };

    if (isGenerating && !parsedData) {
        return (
            <div className="h-full flex flex-col pt-[15%] items-center space-y-4 text-[var(--muted)]">
                <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
                <p className="animate-pulse">AIがノード分析とリサーチプランを生成中...</p>

                {/* プレビュー表示 */}
                <div className="w-full max-w-xl bg-gray-50 border p-4 rounded-xl text-xs font-mono whitespace-pre-wrap overflow-hidden h-40 opacity-50 relative">
                    <div className="absolute inset-0 bg-gradient-to-b from-transparent to-gray-50/90 pointer-events-none" />
                    {rawStreamText || "接続待機中..."}
                </div>
            </div>
        );
    }

    if (!parsedData) {
        return (
            <div className="h-full flex flex-col pt-[20%] items-center text-[var(--muted)]">
                <Search className="w-12 h-12 mb-4 opacity-20" />
                <p>左側のパネルからノードとツールを選択し、生成を開始してください</p>
            </div>
        );
    }

    // Tabs Navigation
    return (
        <div className="h-full flex flex-col bg-white border rounded-xl overflow-hidden shadow-sm">
            <div className="flex border-b bg-gray-50/50 p-2 gap-2">
                <button
                    onClick={() => setActiveTab('gaps')}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === 'gaps' ? 'bg-white shadow-sm text-blue-600 border' : 'text-gray-600 hover:bg-gray-100'}`}
                >
                    <div className="flex items-center gap-2"><AlertCircle className="w-4 h-4" /> 知識ギャップ</div>
                </button>
                <button
                    onClick={() => setActiveTab('instructions')}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === 'instructions' ? 'bg-white shadow-sm text-fuchsia-600 border' : 'text-gray-600 hover:bg-gray-100'}`}
                >
                    <div className="flex items-center gap-2"><FileText className="w-4 h-4" /> リサーチ指示書</div>
                </button>
                <button
                    onClick={() => setActiveTab('rag')}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === 'rag' ? 'bg-white shadow-sm text-emerald-600 border' : 'text-gray-600 hover:bg-gray-100'}`}
                >
                    <div className="flex items-center gap-2"><Database className="w-4 h-4" /> RAG投入データ</div>
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">

                {/* 知識ギャップ */}
                {activeTab === 'gaps' && (
                    <div className="space-y-4">
                        <h3 className="font-semibold text-gray-800 text-lg mb-4 flex items-center gap-2">
                            <span className="w-2 h-6 bg-blue-500 rounded-full"></span>
                            分析結果：{node?.label} の知識ギャップ
                        </h3>
                        <ul className="space-y-3">
                            {parsedData.gaps.map((gap, idx) => (
                                <li key={idx} className="flex gap-3 items-start bg-blue-50/50 p-4 rounded-xl border border-blue-100">
                                    <div className="mt-0.5 text-blue-500">•</div>
                                    <div className="text-gray-700 leading-relaxed">{gap}</div>
                                </li>
                            ))}
                            {parsedData.gaps.length === 0 && <p className="text-gray-500 italic">ギャップが見つかりませんでした。</p>}
                        </ul>
                    </div>
                )}

                {/* リサーチ指示書 */}
                {activeTab === 'instructions' && (
                    <div className="space-y-4 md:flex md:space-x-4 md:space-y-0 h-full">
                        {/* 左：ツールリスト */}
                        <div className="w-full md:w-1/3 flex flex-col space-y-2">
                            {parsedData.instructions.map((inst, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => setActiveToolIndex(idx)}
                                    className={`text-left px-4 py-3 rounded-xl border text-sm font-medium transition-all
                                        ${activeToolIndex === idx
                                            ? 'bg-fuchsia-50 border-fuchsia-200 text-fuchsia-800 shadow-sm'
                                            : 'bg-white border-gray-200 hover:border-gray-300'}
                                    `}
                                >
                                    {inst.tool}
                                </button>
                            ))}
                        </div>
                        {/* 右：プロンプト表示エリア */}
                        <div className="w-full md:w-2/3 bg-gray-900 rounded-xl border border-gray-800 overflow-hidden flex flex-col h-full min-h-[400px]">
                            <div className="flex justify-between items-center bg-gray-800 px-4 py-2 border-b border-gray-700">
                                <span className="text-xs text-gray-300 font-mono flex items-center gap-2">
                                    <FileText className="w-3 h-3" />
                                    prompt_{parsedData.instructions[activeToolIndex]?.tool.replace(/\s+/g, '_').toLowerCase()}.txt
                                </span>
                                <button
                                    onClick={() => handleCopy(parsedData.instructions[activeToolIndex]?.instruction, 'inst')}
                                    className="text-gray-400 hover:text-white transition-colors"
                                >
                                    {copiedStates['inst'] ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                                </button>
                            </div>
                            <div className="p-4 overflow-y-auto flex-1 text-gray-300 font-mono text-sm whitespace-pre-wrap leading-relaxed">
                                {parsedData.instructions[activeToolIndex]?.instruction || "生成データがありません"}
                            </div>
                        </div>
                    </div>
                )}

                {/* RAG投入データ */}
                {activeTab === 'rag' && (
                    <div className="space-y-6">
                        <div className="flex justify-between items-center bg-emerald-50 p-4 border border-emerald-100 rounded-xl">
                            <div>
                                <h3 className="font-semibold text-emerald-900 flex items-center gap-2">
                                    <Database className="w-5 h-5 text-emerald-600" />
                                    Knowledge Item Generator
                                </h3>
                                <p className="text-sm text-emerald-700/80 mt-1">
                                    生成された項目はベクトルデータベース(ChromaDB)の <strong>architectural_rag</strong> コレクションに直接書き込まれます。
                                </p>
                            </div>
                            <button
                                onClick={handleInject}
                                disabled={isInjecting || parsedData.knowledgeItems.length === 0}
                                className={`
                                    flex items-center gap-2 px-6 py-2.5 rounded-xl font-medium shadow-sm whitespace-nowrap transition-all
                                    ${isInjecting
                                        ? 'bg-emerald-200 text-emerald-600 cursor-not-allowed'
                                        : 'bg-emerald-600 hover:bg-emerald-700 text-white'}
                                `}
                            >
                                {isInjecting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                                RAGに投入する
                            </button>
                        </div>

                        {injectSuccess && <div className="p-4 bg-green-50 border border-green-200 text-green-700 rounded-xl flex items-center gap-2"><Check className="w-5 h-5" /> {injectSuccess}</div>}
                        {injectError && <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl flex items-center gap-2"><AlertCircle className="w-5 h-5" /> {injectError}</div>}

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {parsedData.knowledgeItems.map((item, idx) => (
                                <div key={idx} className="border border-gray-200 rounded-xl p-5 hover:border-emerald-300 transition-colors bg-white shadow-sm flex flex-col">
                                    <h4 className="font-bold text-gray-800 mb-2">{item.title}</h4>
                                    <div className="flex flex-wrap gap-1.5 mb-4">
                                        {item.tags.map(tag => (
                                            <span key={tag} className="bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-md text-xs font-medium border border-emerald-100">
                                                #{tag}
                                            </span>
                                        ))}
                                    </div>
                                    <p className="text-sm text-gray-600 leading-relaxed bg-gray-50 flex-1 p-3 rounded-lg border border-gray-100">
                                        {item.content}
                                    </p>
                                    <div className="mt-4 pt-3 border-t flex justify-between items-center text-xs text-[var(--muted)]">
                                        <code>source: research_planner/{node?.id}</code>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

