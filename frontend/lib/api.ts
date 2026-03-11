export interface SourceFile {
    source_id: string;           // "S1", "S2", ... — LLM引用タグとの対応
    filename: string;
    original_filename?: string;
    source_pdf_name: string;     // 表示用PDF名
    source_pdf: string;          // PDFビューア用ID（空の場合あり）
    source_pdf_hash: string;     // ハッシュルーティング用（空の場合あり）
    rel_path: string;            // knowledge_base相対パス
    category: string;
    doc_type: string;            // "drawing" | "law" | "spec" | "catalog" | ""
    pages: number[];             // 参照ページ番号（全件・昇順）
    hit_count: number;           // チャンクヒット数（関連度の目安）
    relevance_count: number;     // hit_countの後方互換エイリアス
}

export interface WebSource {
    title: string;
    url: string;
}

export type StreamUpdate =
    | { type: 'sources'; data: SourceFile[] }
    | { type: 'web_sources'; data: WebSource[] }
    | { type: 'answer'; data: string }
    | { type: 'error'; data: string }
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

export interface SessionSummary {
    id: string;
    title: string | null;
    created_at: string;
    updated_at: string;
}

export interface SessionDetail extends SessionSummary {
    messages: {
        id: number;
        role: 'user' | 'assistant';
        content: string;
        sources?: SourceFile[];
        web_sources?: WebSource[];
        model: string;
        created_at: string;
    }[];
}

export interface SaveMessagePayload {
    user: string;
    assistant: string;
    sources: SourceFile[];
    web_sources?: WebSource[];
    model: string;
}

export interface ProjectInfo {
    id: string;
    name: string;
    status: string;
    building_type: string;
}

export interface ActiveScope {
    project_id: string | null;
    scope_mode: string;
    project_name?: string | null;
}

export async function fetchProjects(): Promise<ProjectInfo[]> {
    const res = await authFetch(`${API_BASE}/api/mindmap/projects`);
    if (!res.ok) throw new Error(`Failed to fetch projects: ${res.statusText}`);
    const data = await res.json();
    return data.projects || [];
}

export async function fetchActiveScope(): Promise<ActiveScope> {
    const res = await authFetch(`${API_BASE}/api/system/active-scope`);
    if (!res.ok) throw new Error(`Failed to fetch active scope: ${res.statusText}`);
    return res.json();
}

export async function updateActiveScope(project_id: string | null, scope_mode: string): Promise<void> {
    const res = await authFetch(`${API_BASE}/api/system/active-scope`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id, scope_mode })
    });
    if (!res.ok) throw new Error(`Failed to update active scope: ${res.statusText}`);
}

/** 利用可能なモデル一覧取得 */
export async function fetchModels(): Promise<Record<string, string>> {
    const res = await authFetch(`${API_BASE}/api/models`);
    if (!res.ok) throw new Error(`Failed to fetch models: ${res.statusText}`);
    return res.json();
}

/** セッション一覧取得 */
export async function fetchSessions(): Promise<SessionSummary[]> {
    const res = await authFetch(`${API_BASE}/api/chat/sessions`);
    if (!res.ok) throw new Error(`Failed to list sessions: ${res.statusText}`);
    return res.json();
}

/** 新規セッション作成 */
export async function createSession(): Promise<{ id: string }> {
    const res = await authFetch(`${API_BASE}/api/chat/sessions`, { method: 'POST' });
    if (!res.ok) throw new Error(`Failed to create session: ${res.statusText}`);
    return res.json();
}

/** セッション詳細取得 */
export async function fetchSessionDetail(id: string): Promise<SessionDetail> {
    const res = await authFetch(`${API_BASE}/api/chat/sessions/${id}`);
    if (!res.ok) throw new Error(`Failed to get session ${id}: ${res.statusText}`);
    return res.json();
}

/** セッション削除 */
export async function deleteSession(id: string): Promise<void> {
    const res = await authFetch(`${API_BASE}/api/chat/sessions/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`Failed to delete session ${id}: ${res.statusText}`);
}

/** 1ターンのメッセージ保存 */
export async function saveMessages(sessionId: string, payload: SaveMessagePayload): Promise<void> {
    const res = await authFetch(`${API_BASE}/api/chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(typeof getAuthHeaders === 'function' ? getAuthHeaders() : {})
        },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Failed to save messages for session: ${res.statusText}`);
}

/** チャットストリーム（モデル選択・コンテキストシート注入対応・キャンセル対応） */
export async function* chatStream(params: {
    question: string;
    session_id?: string;
    category?: string;
    file_type?: string;
    date_range?: string;
    tags?: string[];
    tag_match_mode?: "any" | "all";
    history?: HistoryMessage[];
    model?: string;
    contextSheet?: string | null;
    quickMode?: boolean;
    project_id?: string | null;
    scope_mode?: string;
    use_rag?: boolean;
    use_web_search?: boolean;
    signal?: AbortSignal;
}): AsyncGenerator<StreamUpdate> {
    const {
        question,
        session_id,
        category,
        file_type,
        date_range,
        tags,
        tag_match_mode,
        history,
        model,
        contextSheet,
        quickMode = true,
        project_id,
        scope_mode,
        use_rag = true,
        use_web_search = false,
        signal,
    } = params;

    const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
            question,
            session_id: session_id || null,
            category: category || null,
            file_type: file_type || null,
            date_range: date_range || null,
            tags: tags || null,
            tag_match_mode: tag_match_mode || "any",
            history: history || [],
            model: model || 'gemini-3-flash-preview',
            context_sheet: contextSheet || null,
            quick_mode: quickMode,
            project_id: project_id || null,
            scope_mode: scope_mode || 'auto',
            use_rag: use_rag,
            use_web_search: use_web_search,
        }),
        signal
    });
    
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(err.detail || `API Error: ${response.statusText}`);
    }
    
    if (!response.body) throw new Error('Response body is null');
    yield* _readSSEStream(response.body);
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
    if (!response.body) throw new Error('Response body is null');
    yield* _readSSEStream(response.body);
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

/**
 * SSEストリームを読み込み、イベント単位でパースする共通ヘルパー。
 */
async function* _readSSEStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<StreamUpdate> {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            
            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (const part of parts) {
                if (!part.trim()) continue;

                let eventName = 'message';
                let dataContent = '';
                
                const lines = part.split('\n');
                for (const line of lines) {
                    if (line.startsWith('event:')) {
                        eventName = line.replace('event:', '').trim();
                    } else if (line.startsWith('data:')) {
                        const content = line.replace('data:', '').trim();
                        dataContent += (dataContent ? '\n' : '') + content;
                    }
                }

                if (dataContent === '[DONE]') {
                    yield { type: 'done' };
                    return;
                }

                if (dataContent) {
                    try {
                        const data = JSON.parse(dataContent);
                        if (eventName === 'error') {
                            yield { type: 'error', data: data.error || 'Unknown streaming error' };
                        } else if (data.type === 'web_sources') {
                            yield { type: 'web_sources', data: data.data };
                        } else if (data.type && data.data) {
                            yield data as StreamUpdate;
                        } else if (data.text) {
                            yield { type: 'answer', data: data.text };
                        } else {
                            yield data as StreamUpdate;
                        }
                    } catch (e) {
                        yield { type: 'answer', data: dataContent };
                    }
                }
            }
        }
    } finally {
        reader.cancel().catch(() => {});
        reader.releaseLock();
    }
}
