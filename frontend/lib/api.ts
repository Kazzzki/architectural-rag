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
    | { type: 'truncation_warning'; data: string }
    | { type: 'saved'; id: number }
    | { type: 'done' };

// APIのベースURL (環境変数がない場合はNext.jsの同ドメインリライトに任せる)
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
const API_PASSWORD = process.env.NEXT_PUBLIC_API_PASSWORD || '';

export function getAuthHeaders(): Record<string, string> {
    if (!API_PASSWORD) return {};
    const encoded = typeof btoa !== 'undefined'
        ? btoa(`user:${API_PASSWORD}`)
        : Buffer.from(`user:${API_PASSWORD}`).toString('base64');
    return { Authorization: `Basic ${encoded}` };
}

export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const headers = { ...getAuthHeaders(), ...(options.headers || {}) };

    let cleanUrl = url;
    try {
        if (url.startsWith('/')) {
            // Use window.location.origin to strip credentials from the base URL
            const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
            cleanUrl = baseUrl + url;
        } else {
            const parsedUrl = new URL(url);
            parsedUrl.username = '';
            parsedUrl.password = '';
            cleanUrl = parsedUrl.toString();
        }
    } catch (e) {
        // Ignore parsing errors for relative URLs
    }

    return fetch(cleanUrl, { ...options, headers });
}

export { API_BASE };

export interface HistoryMessage {
    role: 'user' | 'assistant';
    content: string;
}

export interface ContextSheetSummary {
    id: number;
    title: string | null;
    role: string;
    model: string;
    file_count: number;
    truncated: boolean;
    created_at: string;
}

export interface ContextSheetDetail extends ContextSheetSummary {
    file_paths: string[];
    char_limit: number;
    content: string | null;
}

/** チャットストリーム（モデル選択・コンテキストシート注入対応） */
export async function* chatStream(
    question: string,
    category?: string,
    file_type?: string,
    date_range?: string,
    tags?: string[],
    tag_match_mode?: "any" | "all",
    history?: HistoryMessage[],
    model?: string,
    contextSheet?: string | null,
    quickMode: boolean = true,  // デフォルトは高速モード（ストリーム向けにTTFB優先）
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
            model: model || 'gemini-3-flash-preview',
            context_sheet: contextSheet || null,
            quick_mode: quickMode,
        }),
    });
    if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
    yield* _readSSEStream(response);
}

/** コンテキストシート生成（複数ファイル対応SSEストリーム） */
export async function* contextSheetStream(params: {
    file_paths?: string[];
    folder_path?: string;
    role: string;
    model: string;
    char_limit?: number;
    title?: string;
}): AsyncGenerator<StreamUpdate> {
    const response = await fetch(`${API_BASE}/api/analyze/context-sheet`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(params),
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(err.detail || `API Error: ${response.statusText}`);
    }
    yield* _readSSEStream(response);
}

/** 保存済みコンテキストシート一覧を取得 */
export async function listContextSheets(): Promise<ContextSheetSummary[]> {
    const res = await authFetch(`${API_BASE}/api/analyze/context-sheets`);
    if (!res.ok) throw new Error(`Failed to list context sheets: ${res.statusText}`);
    return res.json();
}

/** 特定のコンテキストシート全文を取得 */
export async function getContextSheet(id: number): Promise<ContextSheetDetail> {
    const res = await authFetch(`${API_BASE}/api/analyze/context-sheet/${id}`);
    if (!res.ok) throw new Error(`Failed to get context sheet ${id}: ${res.statusText}`);
    return res.json();
}

/** コンテキストシートを削除 */
export async function deleteContextSheet(id: number): Promise<void> {
    const res = await authFetch(`${API_BASE}/api/analyze/context-sheet/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`Failed to delete context sheet ${id}: ${res.statusText}`);
}

/** 共通SSEリーダー */
async function* _readSSEStream(response: Response): AsyncGenerator<StreamUpdate> {
    const reader = response.body?.getReader();
    if (!reader) throw new Error('Response body is null');
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (line.trim() === '') continue;
            if (line.startsWith('event: error')) {
                // Next line should be data: {"error": "..."}
                continue;
            }
            if (line.startsWith('data: ')) {
                const dataStr = line.slice(6);
                if (dataStr === '[DONE]') { yield { type: 'done' }; return; }
                try {
                    const parsed = JSON.parse(dataStr);
                    if (parsed.error) {
                        throw new Error(parsed.error);
                    }
                    yield parsed;
                } catch (e) {
                    if (e instanceof Error && e.message !== 'Unexpected end of JSON input') {
                        throw e; // throw backend errors to be caught in page.tsx
                    }
                    console.warn('SSE parse error:', e);
                }
            }
        }
    }
}
