export interface SourceFile {
    filename: string;
    original_filename?: string;
    category: string;
    relevance_count: number;
    source_pdf?: string;
    pages?: number[];
}

export type StreamUpdate =
    | { type: 'sources'; data: SourceFile[] }
    | { type: 'answer'; data: string }
    | { type: 'done' };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const API_PASSWORD = process.env.NEXT_PUBLIC_API_PASSWORD || '';

/** Basic認証ヘッダーを生成 */
export function getAuthHeaders(): Record<string, string> {
    if (!API_PASSWORD) return {};
    const encoded = typeof btoa !== 'undefined'
        ? btoa(`user:${API_PASSWORD}`)
        : Buffer.from(`user:${API_PASSWORD}`).toString('base64');
    return { Authorization: `Basic ${encoded}` };
}

/** 認証付きfetch（API_PASSWORDが設定されていればBasic Authヘッダーを自動付与） */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const headers = {
        ...getAuthHeaders(),
        ...(options.headers || {}),
    };
    return fetch(url, { ...options, headers });
}

export { API_BASE };

export interface HistoryMessage {
    role: 'user' | 'assistant';
    content: string;
}

export async function* chatStream(
    question: string,
    category?: string,
    file_type?: string,
    date_range?: string,
    tags?: string[],
    tag_match_mode?: "any" | "all",
    history?: HistoryMessage[],
): AsyncGenerator<StreamUpdate> {
    const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
            question,
            category: category || null,
            file_type: file_type || null,
            date_range: date_range || null,
            tags: tags || null,
            tag_match_mode: tag_match_mode || "any",
            history: history || [],
        }),
    });

    if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('Response body is null');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');

        // Keep the last incomplete line in buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (line.trim() === '') continue;
            if (line.startsWith('data: ')) {
                const dataStr = line.slice(6);
                if (dataStr === '[DONE]') {
                    yield { type: 'done' };
                    return;
                }
                try {
                    const data = JSON.parse(dataStr);
                    yield data;
                } catch (e) {
                    console.warn('JSON parse error:', e, line);
                }
            }
        }
    }
}
