export interface PdfSource {
    source_pdf?: string;
    source_pdf_hash?: string;
    rel_path?: string;
}

export function resolvePdfUrl(src: PdfSource): string | null {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || '';

    // 1位: source_pdf または source_pdf_hash が存在
    const hash = src.source_pdf || src.source_pdf_hash;
    if (hash) {
        return `${apiBase}/api/pdf/${hash}`;
    }

    // 2位: rel_path が .pdf で終わる
    if (src.rel_path && src.rel_path.toLowerCase().endsWith('.pdf')) {
        return `${apiBase}/api/pdf/by-path?p=${encodeURIComponent(src.rel_path)}`;
    }

    // 3位: null（MDで元PDFなし → SourceCard でリンク非表示）
    return null;
}
