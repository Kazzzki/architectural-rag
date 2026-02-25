'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Check, AlertCircle, RefreshCw, Layout, List, Database } from 'lucide-react';
import { ResearchGenerateRequest, ResearchInjectRequest, ParsedResearchResponse, KnowledgeItem } from '../../types/research';

// ProcessNodeの簡易型定義（必要なものだけ）
interface ProcessNode {
    id: string;
    label: string;
    description: string;
    phase: string;
    category: string;
    checklist: string[];
    deliverables: string[];
    ragResults?: any[];
}

interface ResearchTabProps {
    node: ProcessNode;
    onUpdate?: (nodeId: string, updates: Partial<ProcessNode>) => void;
}

const AVAILABLE_TOOLS = [
    { id: 'Gemini Deep Research', label: 'Gemini Deep Research', default: true },
    { id: 'Claude web_fetch', label: 'Claude web_fetch', default: true },
    { id: 'Perplexity', label: 'Perplexity', default: false },
    { id: 'Hikari', label: 'Hikari', default: false }
];

export default function ResearchTab({ node, onUpdate }: ResearchTabProps) {
    const [selectedTools, setSelectedTools] = useState<string[]>(
        AVAILABLE_TOOLS.filter(t => t.default).map(t => t.id)
    );
    const [focus, setFocus] = useState<string>('');
    const [isGenerating, setIsGenerating] = useState<boolean>(false);
    const [rawStreamData, setRawStreamData] = useState<string>('');
    const [parsedData, setParsedData] = useState<ParsedResearchResponse | null>(null);
    const [activeSubTab, setActiveSubTab] = useState<'gaps' | 'instructions' | 'rag'>('gaps');
    const [injectStatus, setInjectStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
    const [injectMessage, setInjectMessage] = useState<string>('');

    // Auto-scroll ref
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (isGenerating && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [rawStreamData, isGenerating]);

    const toggleTool = (toolId: string) => {
        setSelectedTools(prev =>
            prev.includes(toolId)
                ? prev.filter(id => id !== toolId)
                : [...prev, toolId]
        );
    };

    const parseResponseText = (text: string): ParsedResearchResponse => {
        const result: ParsedResearchResponse = {
            gaps: [],
            instructions: [],
            knowledgeItems: []
        };

        const gapMatch = text.match(/---GAP_ANALYSIS---([\s\S]*?)(?=---TOOL_INSTRUCTIONS---)/);
        if (gapMatch && gapMatch[1]) {
            result.gaps = gapMatch[1].split('\n')
                .map(line => line.trim())
                .filter(line => line.startsWith('・') || line.startsWith('-'))
                .map(line => line.replace(/^[・-]\s*/, ''));
        }

        const toolsMatch = text.match(/---TOOL_INSTRUCTIONS---([\s\S]*?)(?=---KNOWLEDGE_ITEMS---)/);
        if (toolsMatch && toolsMatch[1]) {
            const toolBlocks = toolsMatch[1].split('TOOL:').filter(b => b.trim());
            for (const block of toolBlocks) {
                const lines = block.trim().split('\n');
                if (lines.length > 0) {
                    const toolName = lines[0].trim();
                    const instruction = lines.slice(1).join('\n').trim();
                    if (toolName && instruction) {
                        result.instructions.push({ tool: toolName, instruction });
                    }
                }
            }
        }

        const kbMatch = text.match(/---KNOWLEDGE_ITEMS---([\s\S]*?)(?=---END---)/);
        if (kbMatch && kbMatch[1]) {
            const itemBlocks = kbMatch[1].split('ITEM:').filter(b => b.trim());
            for (const block of itemBlocks) {
                const lines = block.trim().split('\n');
                if (lines.length > 0) {
                    const title = lines[0].trim();
                    let tags: string[] = [];
                    let content = '';

                    const tagsLine = lines.find(l => l.startsWith('TAGS:'));
                    if (tagsLine) {
                        tags = tagsLine.replace('TAGS:', '').split(',').map(t => t.trim()).filter(t => t);
                    }

                    const contentIdx = lines.findIndex(l => l.startsWith('CONTENT:'));
                    if (contentIdx !== -1) {
                        content = lines.slice(contentIdx).join('\n').replace('CONTENT:', '').trim();
                    }

                    if (title && content) {
                        result.knowledgeItems.push({ title, tags, content });
                    }
                }
            }
        }

        return result;
    };

    const handleGenerate = async () => {
        setIsGenerating(true);
        setRawStreamData('');
        setParsedData(null);
        setInjectStatus('idle');
        setInjectMessage('');

        const reqBody: ResearchGenerateRequest = {
            node_id: node.id,
            node_label: node.label,
            node_phase: node.phase,
            node_category: node.category,
            node_description: node.description || '',
            node_checklist: node.checklist || [],
            node_deliverables: node.deliverables || [],
            selected_tools: selectedTools,
            focus: focus,
        };

        try {
            const response = await fetch('http://localhost:8000/api/research/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reqBody)
            });

            if (!response.body) throw new Error('No response body');

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let accumulatedData = '';

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.replace('data: ', '');
                            if (dataStr === '[DONE]') {
                                break;
                            }
                            try {
                                const dataObj = JSON.parse(dataStr);
                                if (dataObj.type === 'chunk') {
                                    accumulatedData += dataObj.data;
                                    setRawStreamData(accumulatedData);
                                } else if (dataObj.type === 'parsed') {
                                    const parsed = parseResponseText(dataObj.data);
                                    setParsedData(parsed);
                                }
                            } catch (e) {
                                // Ignore parse errors for partial chunks
                            }
                        }
                    }
                }
            } finally {
                reader.releaseLock();
            }
        } catch (error: any) {
            console.error('Failed to generate research plan:', error);
            setRawStreamData(`生成中にエラーが発生しました: ${error.message}`);
        } finally {
            setIsGenerating(false);
        }
    };

    const handleInject = async () => {
        if (!parsedData || parsedData.knowledgeItems.length === 0) return;

        setIsGenerating(true);
        setInjectStatus('loading');
        setInjectMessage('データベースへ投入中...');

        const timestamp = Date.now().toString();

        const itemsToInject: KnowledgeItem[] = parsedData.knowledgeItems.map((k, i) => ({
            id: `ki_${node.id}_${timestamp}_${i}`,
            title: k.title,
            tags: k.tags,
            content: k.content
        }));

        const reqBody: ResearchInjectRequest = {
            node_id: node.id,
            node_label: node.label,
            node_phase: node.phase,
            node_category: node.category,
            items: itemsToInject
        };

        try {
            const response = await fetch('http://localhost:8000/api/research/inject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reqBody)
            });

            const result = await response.json();

            if (response.ok) {
                setInjectStatus('success');
                setInjectMessage(`✅ ${result.injected}件のデータを投入しました。`);

                // RAG検索タブなどに反映するため、NodeUpdate経由で node.ragResults に追加する
                if (onUpdate) {
                    const newRagResults = itemsToInject.map(item => ({
                        id: item.id,
                        content: item.content,
                        metadata: {
                            source: `research_planner/${node.id}`,
                            title: item.title,
                            tags: item.tags.join(','),
                            created_at: new Date().toISOString()
                        }
                    }));

                    const existingRagResults = node.ragResults || [];
                    onUpdate(node.id, { ragResults: [...newRagResults, ...existingRagResults] });
                }
            } else {
                setInjectStatus('error');
                setInjectMessage(`❌ エラー: ${result.detail || '投入に失敗しました'}`);
            }
        } catch (error: any) {
            setInjectStatus('error');
            setInjectMessage(`❌ エラー: ${error.message}`);
        } finally {
            setIsGenerating(false);
        }
    };

    return (
        <div className="flex flex-col gap-4">
            {/* Input Controls */}
            <div className="bg-[var(--background)] p-4 rounded-lg border border-[var(--border)]">
                <div className="mb-3">
                    <label className="text-xs font-bold text-[var(--muted)] mb-2 block">リサーチ対象フォーカス (任意)</label>
                    <input
                        type="text"
                        value={focus}
                        onChange={(e) => setFocus(e.target.value)}
                        placeholder="例: 法規制における最新の改正点について深掘りしたい"
                        className="w-full bg-[var(--background)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--foreground)]"
                    />
                </div>

                <div className="mb-4">
                    <label className="text-xs font-bold text-[var(--muted)] mb-2 block">使用ツール選択</label>
                    <div className="flex flex-wrap gap-2">
                        {AVAILABLE_TOOLS.map(tool => (
                            <label key={tool.id} className="flex items-center gap-1.5 cursor-pointer bg-[var(--background)] border border-[var(--border)] px-2.5 py-1.5 rounded-md hover:bg-slate-50 transition-colors">
                                <input
                                    type="checkbox"
                                    checked={selectedTools.includes(tool.id)}
                                    onChange={() => toggleTool(tool.id)}
                                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                />
                                <span className="text-xs text-[var(--foreground)]">{tool.label}</span>
                            </label>
                        ))}
                    </div>
                </div>

                <button
                    onClick={handleGenerate}
                    disabled={isGenerating || selectedTools.length === 0}
                    className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm py-2 px-4 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {isGenerating && !parsedData ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                        <Send className="w-4 h-4" />
                    )}
                    {isGenerating && !parsedData ? '生成中...' : 'リサーチ計画を生成'}
                </button>
            </div>

            {/* Results Output */}
            {(!parsedData && rawStreamData) && (
                <div className="bg-slate-900 text-slate-300 p-4 rounded-lg font-mono text-xs overflow-y-auto max-h-64 whitespace-pre-wrap" ref={scrollRef}>
                    {rawStreamData}
                </div>
            )}

            {parsedData && (
                <div className="border border-[var(--border)] rounded-lg overflow-hidden flex flex-col">
                    {/* Tabs */}
                    <div className="flex border-b border-[var(--border)] bg-slate-50">
                        <button
                            className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-xs font-medium transition-colors ${activeSubTab === 'gaps' ? 'bg-white text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'}`}
                            onClick={() => setActiveSubTab('gaps')}
                        >
                            <AlertCircle className="w-3.5 h-3.5" /> ギャップ
                            <span className="bg-slate-100 text-slate-500 text-[10px] px-1.5 rounded-full">{parsedData.gaps.length}</span>
                        </button>
                        <button
                            className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-xs font-medium transition-colors ${activeSubTab === 'instructions' ? 'bg-white text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'}`}
                            onClick={() => setActiveSubTab('instructions')}
                        >
                            <List className="w-3.5 h-3.5" /> 指示書
                            <span className="bg-slate-100 text-slate-500 text-[10px] px-1.5 rounded-full">{parsedData.instructions.length}</span>
                        </button>
                        <button
                            className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-xs font-medium transition-colors ${activeSubTab === 'rag' ? 'bg-white text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'}`}
                            onClick={() => setActiveSubTab('rag')}
                        >
                            <Database className="w-3.5 h-3.5" /> RAG情報
                            <span className="bg-slate-100 text-slate-500 text-[10px] px-1.5 rounded-full">{parsedData.knowledgeItems.length}</span>
                        </button>
                    </div>

                    {/* Tab Content */}
                    <div className="p-4 bg-white max-h-96 overflow-y-auto">
                        {activeSubTab === 'gaps' && (
                            <ul className="space-y-3">
                                {parsedData.gaps.map((gap, i) => (
                                    <li key={i} className="flex gap-2 text-sm text-[var(--foreground)]">
                                        <div className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0 mt-1.5" />
                                        <span className="leading-relaxed">{gap}</span>
                                    </li>
                                ))}
                                {parsedData.gaps.length === 0 && <p className="text-xs text-slate-500">抽出されたギャップ項目がありません。</p>}
                            </ul>
                        )}

                        {activeSubTab === 'instructions' && (
                            <div className="space-y-5">
                                {parsedData.instructions.map((inst, i) => (
                                    <div key={i} className="border border-slate-200 rounded-lg overflow-hidden">
                                        <div className="bg-slate-100 px-3 py-2 border-b border-slate-200 flex justify-between items-center">
                                            <span className="text-xs font-bold text-slate-700">{inst.tool}</span>
                                            <button
                                                onClick={() => navigator.clipboard.writeText(inst.instruction)}
                                                className="text-[10px] bg-white border border-slate-300 px-2 py-1 rounded shadow-sm hover:bg-slate-50 active:bg-slate-100 transition-colors"
                                            >
                                                コピー
                                            </button>
                                        </div>
                                        <div className="p-3 bg-white font-mono text-xs text-slate-800 whitespace-pre-wrap">
                                            {inst.instruction}
                                        </div>
                                    </div>
                                ))}
                                {parsedData.instructions.length === 0 && <p className="text-xs text-slate-500">生成された指示書がありません。</p>}
                            </div>
                        )}

                        {activeSubTab === 'rag' && (
                            <div className="space-y-4">
                                {parsedData.knowledgeItems.map((item, i) => (
                                    <div key={i} className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                                        <h4 className="font-bold text-sm text-slate-800 mb-2">{item.title}</h4>
                                        <div className="flex flex-wrap gap-1 mb-2">
                                            {item.tags.map((tag, j) => (
                                                <span key={j} className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                                                    #{tag}
                                                </span>
                                            ))}
                                        </div>
                                        <p className="text-xs text-slate-600 leading-relaxed">{item.content}</p>
                                    </div>
                                ))}

                                {parsedData.knowledgeItems.length > 0 && (
                                    <div className="mt-4 pt-4 border-t border-slate-200">
                                        <button
                                            onClick={handleInject}
                                            disabled={injectStatus === 'loading'}
                                            className="w-full flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-900 text-white font-medium text-xs py-2 px-4 rounded transition-colors disabled:opacity-50"
                                        >
                                            {injectStatus === 'loading' ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Database className="w-3.5 h-3.5" />}
                                            ChromaDBにナレッジとして投入
                                        </button>

                                        {injectMessage && (
                                            <div className={`mt-3 text-xs p-2 rounded flex items-center gap-1.5 ${injectStatus === 'success' ? 'bg-green-50 text-green-700 border border-green-200' :
                                                    injectStatus === 'error' ? 'bg-red-50 text-red-700 border border-red-200' :
                                                        'bg-slate-50 text-slate-600'
                                                }`}>
                                                {injectStatus === 'success' && <Check className="w-3.5 h-3.5" />}
                                                {injectStatus === 'error' && <AlertCircle className="w-3.5 h-3.5" />}
                                                {injectMessage}
                                            </div>
                                        )}
                                    </div>
                                )}
                                {parsedData.knowledgeItems.length === 0 && <p className="text-xs text-slate-500">投入可能なRAGデータがありません。</p>}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
