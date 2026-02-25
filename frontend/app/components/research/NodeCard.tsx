import React from 'react';
import { PipelineNode } from '../../types/research';
import { Server, Database, Code, RefreshCw, GitMerge } from 'lucide-react';

interface NodeCardProps {
    node: PipelineNode;
    isSelected: boolean;
    onClick: () => void;
}

export default function NodeCard({ node, isSelected, onClick }: NodeCardProps) {
    const getIcon = () => {
        switch (node.id) {
            case 'ingestion': return <Database className="w-5 h-5" />;
            case 'retrieval': return <Server className="w-5 h-5" />;
            case 'generation': return <Code className="w-5 h-5" />;
            case 'routing': return <RefreshCw className="w-5 h-5" />;
            case 'data_layer': return <GitMerge className="w-5 h-5" />;
            default: return <Server className="w-5 h-5" />;
        }
    };

    return (
        <button
            onClick={onClick}
            className={`
                flex flex-col items-start p-4 rounded-xl border transition-all text-left min-w-[200px]
                ${isSelected
                    ? 'border-blue-500 bg-blue-50 shadow-sm ring-1 ring-blue-500 text-blue-900'
                    : 'border-[var(--border)] bg-[var(--card)] hover:border-gray-300 hover:bg-gray-50'
                }
            `}
        >
            <div className={`flex items-center gap-2 mb-2 ${isSelected ? 'text-blue-600' : 'text-gray-700'}`}>
                {getIcon()}
                <span className="font-semibold">{node.label}</span>
            </div>
            <p className={`text-xs ${isSelected ? 'text-blue-800/80' : 'text-[var(--muted)]'} line-clamp-2`}>
                {node.description}
            </p>
            <div className={`mt-3 flex gap-1 flex-wrap`}>
                {node.components.slice(0, 2).map((comp, i) => (
                    <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded-full ${isSelected ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}`}>
                        {comp}
                    </span>
                ))}
            </div>
        </button>
    );
}
