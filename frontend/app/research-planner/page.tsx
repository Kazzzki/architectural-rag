'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { Building2, ArrowLeft, RefreshCw, Send, Settings, BookOpen } from 'lucide-react';
import { PipelineNode, ParsedResearchResponse, ResearchGenerateRequest } from '../types/research';
import NodeCard from '../components/research/NodeCard';
import ResultPanel from '../components/research/ResultPanel';
import { authFetch } from '../../lib/api';

const API_BASE = "";

const AVAILABLE_TOOLS = [
    "Gemini Deep Research",
    "Claude web_fetch",
    "Perplexity Pro",
    "arXiv Explorer",
    "Gemini Code Assist",
    "Github Issues/Discussions"
];

const CATEGORIES = [
    { value: 'rag_retrieval', label: 'RAG Retrieval (検索)' },
    { value: 'rag_ingestion', label: 'RAG Ingestion (データ投入)' },
    { value: 'rag_generation', label: 'RAG Generation (回答生成)' },
    { value: 'system_design', label: 'System Design (設計)' }
];

export default function ResearchPlannerPage() {
    const [nodes, setNodes] = useState<PipelineNode[]>([]);
    const [selectedNode, setSelectedNode] = useState<PipelineNode | null>(null);
    const [isLoadingInit, setIsLoadingInit] = useState(true);

    // Setting Panel State
    const [selectedTools, setSelectedTools] = useState<string[]>([]);
    const [searchCategory, setSearchCategory] = useState('rag_retrieval');
    const [focusArea, setFocusArea] = useState('');
    const [extraContext, setExtraContext] = useState('');

    // Generation State
    const [isGenerating, setIsGenerating] = useState(false);
    const [rawStreamText, setRawStreamText] = useState('');
    const [parsedData, setParsedData] = useState<ParsedResearchResponse | null>(null);
    const [generateError, setGenerateError] = useState<string | null>(null);

    useEffect(() => {
        const fetchNodes = async () => {
            try {
                const res = await authFetch(`${API_BASE}/api/research/nodes`);
                if (res.ok) {
                    const data = await res.json();
                    setNodes(data);
                    if (data.length > 0) {
                        handleNodeSelect(data[0]);
                    }
                }
            } catch (err) {
                console.error("Failed to load nodes", err);
            } finally {
                setIsLoadingInit(false);
            }
        };
        fetchNodes();
    }, []);

    const handleNodeSelect = (node: PipelineNode) => {
        setSelectedNode(node);
        setSelectedTools(node.default_tools || []);
        setSearchCategory(
            node.id === 'retrieval' ? 'rag_retrieval' :
                node.id === 'ingestion' ? 'rag_ingestion' :
                    node.id === 'generation' ? 'rag_generation' : 'system_design'
        );
        // リセット
        setFocusArea('');
        setExtraContext('');
        setParsedData(null);
        setRawStreamText('');
        setGenerateError(null);
    };

    const toggleTool = (tool: string) => {
        setSelectedTools(prev =>
            prev.includes(tool) ? prev.filter(t => t !== tool) : [...prev, tool]
        );
    };

    // --- Parser Helper ---
    const parseResearchOutput = (rawText: string): ParsedResearchResponse => {
        const result: ParsedResearchResponse = {
            gaps: [],
            instructions: [],
            knowledgeItems: []
        };

        const gapsMatch = rawText.match(/---GAP_ANALYSIS---([\s\S]*?)(?=---TOOL_INSTRUCTIONS---)/);
        if (gapsMatch) {
            result.gaps = gapsMatch[1].split('\n')
                .map(line => line.trim())
                .filter(line => line.startsWith('・') || line.startsWith('-'))
                .map(line => line.replace(/^[・-]\s*/, ''));
        }

        const toolsMatch = rawText.match(/---TOOL_INSTRUCTIONS---([\s\S]*?)(?=---KNOWLEDGE_ITEMS---)/);
        if (toolsMatch) {
            const toolBlocks = toolsMatch[1].split(/TOOL:\s*/).filter(b => b.trim());
            toolBlocks.forEach(block => {
                const lines = block.split('\n');
                const toolName = lines[0].trim();
                const instruction = lines.slice(1).join('\n').trim();
                if (toolName && instruction) {
                    result.instructions.push({ tool: toolName, instruction });
                }
            });
        }

        const itemsMatch = rawText.match(/---KNOWLEDGE_ITEMS---([\s\S]*?)(?=---END---)/);
        if (itemsMatch) {
            const itemBlocks = itemsMatch[1].split(/ITEM:\s*/).filter(b => b.trim());
            itemBlocks.forEach(block => {
                const tagsMatch = block.match(/TAGS:\s*(.*)/);
                const contentMatch = block.match(/CONTENT:\s*([\s\S]*?)---/);

                const title = block.split('\n')[0].trim();
                const tags = tagsMatch ? tagsMatch[1].split(',').map(t => t.trim()) : [];
                const content = contentMatch ? contentMatch[1].trim() : '';

                if (title && content) {
                    result.knowledgeItems.push({ title, tags, content });
                }
            });
        }

        return result;
    };

    // --- Generate Stream ---
    const handleGenerate = async () => {
        if (!selectedNode || selectedTools.length === 0) return;

        setIsGenerating(true);
        setGenerateError(null);
        setParsedData(null);
        setRawStreamText('');

        try {
            const payload: ResearchGenerateRequest = {
                node_id: selectedNode.id,
                node_label: selectedNode.label,
                node_desc: selectedNode.description,
                node_components: selectedNode.components,
                node_domains: selectedNode.domains,
                search_category: searchCategory,
                doc_type: selectedNode.default_doc_type || 'spec',
                selected_tools: selectedTools,
                focus: focusArea || "全体的な改善点",
                extra_context: extraContext
            };

            const authToken = localStorage.getItem('auth_token');
            const headers: Record<string, string> = {
                'Content-Type': 'application/json'
            };
            if (authToken) {
                headers['Authorization'] = `Basic ${authToken}`;
            }

            const response = await fetch(`${API_BASE}/api/research/generate`, {
                method: 'POST',
                headers,
                body: JSON.stringify(payload)
            });

            if (!response.ok || !response.body) {
                throw new Error('Failed to start stream');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ') && line !== 'data: [DONE]') {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === 'chunk') {
                                setRawStreamText(prev => prev + data.data);
                            } else if (data.type === 'parsed') {
                                // ストリーム完了時に一括パース
                                setParsedData(parseResearchOutput(data.data));
                            }
                        } catch (e) {
                            console.error("Stream parse error:", e);
                        }
                    }
                }
            }
        } catch (error: any) {
            console.error("Generate error:", error);
            setGenerateError(error.message || "生成中にエラーが発生しました");
        } finally {
            setIsGenerating(false);
        }
    };

    if (isLoadingInit) {
        return (
            <div className="min-h-screen bg-[var(--background)] flex items-center justify-center">
                <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#F8FAFC] flex flex-col text-gray-800 font-sans">
            {/* Header */}
            <header className="bg-white border-b border-gray-200 sticky top-0 z-10 shadow-sm">
                <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link href="/" className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-500">
                            <ArrowLeft className="w-5 h-5" />
                        </Link>
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-inner">
                            <BookOpen className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-700 to-indigo-700 bg-clip-text text-transparent">
                                Research Planner
                            </h1>
                            <p className="text-[11px] font-medium text-gray-400 tracking-wide uppercase">AI Pipeline Orchestrator</p>
                        </div>
                    </div>
                </div>
            </header>

            <main className="flex-1 max-w-7xl mx-auto w-full p-4 md:p-6 flex flex-col gap-6">

                {/* 1. Process Map */}
                <section>
                    <div className="flex items-center gap-2 mb-3 px-1 text-sm font-bold text-gray-800 uppercase tracking-wider">
                        <Settings className="w-4 h-4 text-gray-400" />
                        <span>1. パイプライン・ノードの選択</span>
                    </div>
                    <div className="flex gap-3 overflow-x-auto pb-4 scrollbar-hide py-1 px-1">
                        {nodes.map(node => (
                            <NodeCard
                                key={node.id}
                                node={node}
                                isSelected={selectedNode?.id === node.id}
                                onClick={() => handleNodeSelect(node)}
                            />
                        ))}
                    </div>
                </section>

                {/* 2. Main Workspace */}
                <div className="flex flex-col lg:flex-row gap-6 h-[700px]">

                    {/* Settings Panel (Left) */}
                    <aside className="w-full lg:w-[360px] flex flex-col gap-4">
                        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 h-full flex flex-col">
                            <h2 className="text-lg font-bold text-gray-800 mb-5 pb-2 border-b border-gray-100 flex items-center gap-2">
                                <span className="bg-blue-100 text-blue-700 text-xs py-0.5 px-2 rounded-full font-bold">2</span>
                                構成設定
                            </h2>

                            <div className="space-y-6 flex-1 overflow-y-auto pr-2">
                                {/* Tools */}
                                <div>
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">連携エージェント・ツール</label>
                                    <div className="flex flex-wrap gap-2">
                                        {AVAILABLE_TOOLS.map(tool => {
                                            const isSelected = selectedTools.includes(tool);
                                            return (
                                                <button
                                                    key={tool}
                                                    onClick={() => toggleTool(tool)}
                                                    className={`
                                                        px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border
                                                        ${isSelected
                                                            ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                                                            : 'bg-white text-gray-600 hover:bg-gray-50 border-gray-200 hover:border-gray-300'}
                                                    `}
                                                >
                                                    {tool}
                                                </button>
                                            )
                                        })}
                                    </div>
                                </div>

                                {/* Focus Area */}
                                <div>
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">特定フォーカス領域</label>
                                    <input
                                        type="text"
                                        placeholder="例：OCR精度の向上策"
                                        value={focusArea}
                                        onChange={e => setFocusArea(e.target.value)}
                                        className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:bg-white transition-all text-gray-800"
                                    />
                                </div>

                                {/* Category Dropdown */}
                                <div>
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">ナレッジ保存先カテゴリ</label>
                                    <select
                                        value={searchCategory}
                                        onChange={e => setSearchCategory(e.target.value)}
                                        className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:bg-white transition-all text-gray-800"
                                    >
                                        {CATEGORIES.map(cat => (
                                            <option key={cat.value} value={cat.value}>{cat.label}</option>
                                        ))}
                                    </select>
                                </div>

                                {/* Extra Context */}
                                <div>
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">追加コンテキスト</label>
                                    <textarea
                                        placeholder="現状の課題やエラーログなど..."
                                        rows={4}
                                        value={extraContext}
                                        onChange={e => setExtraContext(e.target.value)}
                                        className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:bg-white transition-all resize-none text-gray-800"
                                    />
                                </div>
                            </div>

                            {generateError && (
                                <div className="mt-4 p-3 bg-red-50 text-red-600 text-xs rounded-lg border border-red-100">
                                    {generateError}
                                </div>
                            )}

                            <button
                                onClick={handleGenerate}
                                disabled={isGenerating || selectedTools.length === 0}
                                className={`
                                    mt-6 w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-bold text-sm transition-all
                                    ${isGenerating || selectedTools.length === 0
                                        ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                                        : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-md hover:shadow-lg transform hover:-translate-y-0.5'}
                                `}
                            >
                                {isGenerating ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                                {isGenerating ? 'AIが分析しています...' : 'リサーチプランを生成'}
                            </button>
                        </div>
                    </aside>

                    {/* Result Panel (Right) */}
                    <div className="flex-1 bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
                        <ResultPanel
                            parsedData={parsedData}
                            node={selectedNode}
                            isGenerating={isGenerating}
                            rawStreamText={rawStreamText}
                        />
                    </div>

                </div>
            </main>
        </div>
    );
}
