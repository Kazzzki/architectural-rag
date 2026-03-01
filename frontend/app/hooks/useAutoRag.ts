import { useState, useEffect, useRef } from 'react';
import { authFetch } from '@/lib/api';

interface AutoLinkResult {
    nodeId: string;
    keywords: string[];
    results: {
        id: string;
        source: string;
        content: string;
        relevance: number;
        full_content: string;
    }[];
}

interface UseAutoRagProps {
    projectId: string;
    selectedNode: any | null; // ProcessNode
    onResultsFound: (nodeId: string, results: AutoLinkResult) => void;
}

export function useAutoRag({ projectId, selectedNode, onResultsFound }: UseAutoRagProps) {
    const [isSearching, setIsSearching] = useState(false);
    const lastProcessedNode = useRef<{ id: string; label: string; description: string } | null>(null);
    const timeoutRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        if (!selectedNode) return;

        // Check if node content actually changed significanly
        const current = {
            id: selectedNode.id,
            label: selectedNode.label,
            description: selectedNode.description
        };

        if (
            lastProcessedNode.current &&
            lastProcessedNode.current.id === current.id &&
            lastProcessedNode.current.label === current.label &&
            lastProcessedNode.current.description === current.description
        ) {
            return;
        }

        // Clear existing timer
        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current);
        }

        // Set new timer (debounce 2s)
        timeoutRef.current = setTimeout(async () => {
            // Skip if node selection changed concurrently
            if (selectedNode.id !== current.id) return;

            setIsSearching(true);
            try {
                const res = await authFetch(`/api/mindmap/ai/auto-link`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        nodeId: selectedNode.id,
                        label: selectedNode.label,
                        description: selectedNode.description,
                        projectContext: projectId // Could pass more context if available
                    }),
                });

                if (res.ok) {
                    const data: AutoLinkResult = await res.json();
                    onResultsFound(selectedNode.id, data);
                    lastProcessedNode.current = current;
                }
            } catch (error) {
                console.error("Auto-link failed:", error);
            } finally {
                setIsSearching(false);
            }
        }, 2000); // 2 second debounce

        return () => {
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
        };
    }, [selectedNode, projectId, onResultsFound]);

    return { isSearching };
}
