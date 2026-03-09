export interface PdfSource {
    source_pdf?: string;
    source_pdf_hash?: string;
    rel_path?: string;
    filename?: string;
    original_filename?: string;
    pdf_filename?: string;
}

/** source_pdf_hash から画像ファイルかどうかを判定するのは難しいため、
 *  ファイル名やrel_pathの拡張子で判定する */
function isImageFile(src: PdfSource): boolean {
    const imageExts = /\.(png|jpg|jpeg|gif|webp)$/i;
    return !!(
        (src.filename && imageExts.test(src.filename)) ||
        (src.original_filename && imageExts.test(src.original_filename)) ||
        (src.pdf_filename && imageExts.test(src.pdf_filename)) ||
        (src.rel_path && imageExts.test(src.rel_path)) ||
        (src.source_pdf && imageExts.test(src.source_pdf))
    );
}

export function resolvePdfUrl(src: PdfSource): string | null {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || '';

    // 1位: source_pdf_hash が存在 → ハッシュベースルーティング（最も信頼性が高い）
    const hash = src.source_pdf_hash || src.source_pdf;
    if (hash && hash.trim() && !hash.includes('/') && !hash.includes('.')) {
        return `${apiBase}/api/pdf/${encodeURIComponent(hash)}`;
    }

    // 2位: 画像ファイルの場合（rel_path や source_pdf に画像拡張子が含まれる）
    if (isImageFile(src)) {
        const imgPath = src.rel_path || src.source_pdf;
        if (imgPath) {
            return `${apiBase}/api/pdf/by-path?p=${encodeURIComponent(imgPath)}`;
        }
    }

    // 3位: source_pdf がパス形式（例: "00_未分類/xxx.pdf"）の場合は by-path で配信
    if (src.source_pdf && (src.source_pdf.includes('/') || src.source_pdf.toLowerCase().endsWith('.pdf'))) {
        return `${apiBase}/api/pdf/by-path?p=${encodeURIComponent(src.source_pdf)}`;
    }

    // 4位: rel_path が .pdf で終わる → knowledge_base 相対パスで直接配信
    if (src.rel_path && src.rel_path.toLowerCase().endsWith('.pdf')) {
        return `${apiBase}/api/pdf/by-path?p=${encodeURIComponent(src.rel_path)}`;
    }

    // 5位: rel_path が .md の場合、同名 PDF を探す（OCR元PDFへのフォールバック）
    if (src.rel_path && src.rel_path.toLowerCase().endsWith('.md')) {
        const pdfPath = src.rel_path.replace(/\.md$/i, '.pdf');
        return `${apiBase}/api/pdf/by-path?p=${encodeURIComponent(pdfPath)}`;
    }

    // 6位: null（PDFなし → SourceCard でリンク非表示）
    return null;
}
