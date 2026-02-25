import { NextResponse } from 'next/server';
import { authFetch, API_BASE } from '@/lib/api';

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const { action, nodeId, content, context } = body;

        const response = await authFetch(`${API_BASE}/api/mindmap/ai/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, nodeId, content, context })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Backend error: ${response.status}`);
        }

        const result = await response.json();
        return NextResponse.json(result);

    } catch (error: any) {
        console.error('AI API Error:', error);
        return NextResponse.json({ error: error.message || 'Internal Server Error' }, { status: 500 });
    }
}
