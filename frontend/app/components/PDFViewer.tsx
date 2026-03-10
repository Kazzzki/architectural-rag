'use client';

import { useState, useEffect, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, X, Loader2, AlertCircle, Download } from 'lucide-react';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { getAuthHeaders } from '@/lib/api';

// Worker setup: public/ にコピーしたローカルWorkerを使用する。
// CDN (unpkg) は以下の理由で使わない:
//   1. ネットワーク環境・CSPによりブロックされる場合がある
//   2. バージョン不一致が起きると "The API version does not match" エラーになる
// public/pdf.worker.min.mjs は node_modules/pdfjs-dist/build/pdf.worker.min.mjs と同一ファイル。
pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs';

interface PDFViewerProps {
    url: string | null;
    initialPage?: number;
    onClose: () => void;
}

export default function PDFViewer({ url, initialPage = 1, onClose }: PDFViewerProps) {
    const [numPages, setNumPages] = useState<number | null>(null);
    const [pageNumber, setPageNumber] = useState(initialPage);
    const [scale, setScale] = useState(1.0);
    const [isLoading, setIsLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [isDownloading, setIsDownloading] = useState(false);

    // PDF バイナリを authFetch で取得し Blob URL として保持する。
    // react-pdf の Document コンポーネントは内部で pdfjs Worker を使って
    // PDF を fetch するが、Worker スレッドは window.fetch のパッチ (AuthProvider)
    // が効かないため Authorization ヘッダーが付かず BasicAuth 環境で 401 になる。
    // 解決策: メインスレッドで認証付き fetch → ArrayBuffer → BlobURL に変換して渡す。
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const prevBlobUrlRef = useRef<string | null>(null);
    const [retryCount, setRetryCount] = useState(0);

    useEffect(() => {
        // url が変わったら前回の BlobURL を解放
        return () => {
            if (prevBlobUrlRef.current) {
                URL.revokeObjectURL(prevBlobUrlRef.current);
                prevBlobUrlRef.current = null;
            }
        };
    }, [url]);

    useEffect(() => {
        if (!url) {
            setBlobUrl(null);
            return;
        }

        let cancelled = false;

        const fetchPdf = async () => {
            setIsLoading(true);
            setLoadError(null);
            setBlobUrl(null);

            try {
                const headers = getAuthHeaders();
                const response = await fetch(url, { headers });

                if (cancelled) return;

                if (!response.ok) {
                    const statusText = response.statusText || String(response.status);
                    if (response.status === 401 || response.status === 403) {
                        throw new Error(`認証エラー (${response.status})。NEXT_PUBLIC_API_PASSWORDを確認してください。`);
                    } else if (response.status === 404) {
                        throw new Error(`PDFファイルが見つかりません (404)。ファイルが処理中か、パスが変更された可能性があります。`);
                    }
                    throw new Error(`サーバーエラー: ${statusText} (${response.status})`);
                }

                const blob = await response.blob();
                if (cancelled) return;

                // 前回の BlobURL を解放
                if (prevBlobUrlRef.current) {
                    URL.revokeObjectURL(prevBlobUrlRef.current);
                }

                const newBlobUrl = URL.createObjectURL(blob);
                prevBlobUrlRef.current = newBlobUrl;
                setBlobUrl(newBlobUrl);
            } catch (err) {
                if (cancelled) return;
                const msg = err instanceof Error ? err.message : 'PDFの取得に失敗しました';
                let friendly = msg;
                if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.toLowerCase().includes('network')) {
                    friendly = 'ネットワークエラー。バックエンドサーバーが起動しているか確認してください。';
                }
                setLoadError(friendly);
                setIsLoading(false);
            }
        };

        fetchPdf();

        return () => {
            cancelled = true;
        };
    }, [url, retryCount]);

    // url/initialPage が変わったらページ番号をリセット
    useEffect(() => {
        setPageNumber(Math.max(1, initialPage));
    }, [initialPage, url]);

    const handleDownload = async () => {
        if (!url || isDownloading) return;

        setIsDownloading(true);
        try {
            const fileName = decodeURIComponent(url.split('/').pop()?.split('#')[0] || 'document.pdf');
            const headers = getAuthHeaders();
            const response = await fetch(url, { headers });

            if (!response.ok) throw new Error(`Download failed: ${response.statusText}`);

            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = downloadUrl;
            link.download = fileName;
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(downloadUrl);
        } catch (error) {
            console.error('Error downloading PDF:', error);
            alert('PDFのダウンロードに失敗しました。');
        } finally {
            setIsDownloading(false);
        }
    };

    function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
        setNumPages(numPages);
        setIsLoading(false);
        setLoadError(null);
        setPageNumber(prev => Math.max(1, Math.min(prev, numPages)));
    }

    function onDocumentLoadError(error: Error) {
        console.error('PDFViewer: react-pdf load error:', error, 'blobUrl:', blobUrl);
        setIsLoading(false);
        let msg = error.message || 'PDFの解析に失敗しました';
        if (msg.includes('Invalid PDF') || msg.includes('MissingPDF') || msg.includes('UnexpectedResponseException')) {
            msg = '無効なPDFデータです。OCR処理が完了していないか、ファイルが壊れている可能性があります。';
        }
        setLoadError(msg);
    }

    function changePage(offset: number) {
        setPageNumber(prev => Math.max(1, Math.min(prev + offset, numPages || 1)));
    }

    if (!url) {
        return (
            <div className="flex items-center justify-center h-full text-gray-400">
                <p>PDFを選択してください</p>
            </div>
        );
    }

    const displayName = decodeURIComponent(url.split('/').pop()?.split('?')[0]?.split('#')[0] || 'Document');

    return (
        <div className="flex flex-col h-full bg-gray-100 border-l border-gray-200 relative">
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200 shadow-sm z-10">
                <div className="flex items-center gap-4">
                    <span className="text-sm font-medium text-gray-700 truncate max-w-[200px]" title={displayName}>
                        {displayName}
                    </span>

                    <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
                        <button
                            onClick={() => changePage(-1)}
                            disabled={pageNumber <= 1}
                            className="p-1 hover:bg-white rounded-md disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
                        >
                            <ChevronLeft className="w-4 h-4" />
                        </button>
                        <span className="text-xs font-medium w-16 text-center">
                            {pageNumber} / {numPages || '-'}
                        </span>
                        <button
                            onClick={() => changePage(1)}
                            disabled={pageNumber >= (numPages || 1)}
                            className="p-1 hover:bg-white rounded-md disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
                        >
                            <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>

                    <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
                        <button
                            onClick={() => setScale(prev => Math.max(0.5, prev - 0.1))}
                            className="p-1 hover:bg-white rounded-md transition-colors"
                        >
                            <ZoomOut className="w-4 h-4" />
                        </button>
                        <span className="text-xs font-medium w-12 text-center">
                            {Math.round(scale * 100)}%
                        </span>
                        <button
                            onClick={() => setScale(prev => Math.min(2.0, prev + 0.1))}
                            className="p-1 hover:bg-white rounded-md transition-colors"
                        >
                            <ZoomIn className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                <div className="flex items-center gap-1 text-gray-500">
                    <button
                        onClick={handleDownload}
                        disabled={isDownloading || !url}
                        className="p-1.5 hover:bg-blue-50 hover:text-blue-600 rounded-lg transition-colors disabled:opacity-50"
                        title="ダウンロード"
                    >
                        {isDownloading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Download className="w-5 h-5" />}
                    </button>
                    <button
                        onClick={onClose}
                        className="p-1.5 hover:bg-red-50 hover:text-red-500 rounded-lg transition-colors"
                        title="閉じる"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>
            </div>

            {/* Document Area */}
            <div className="flex-1 overflow-auto p-4 flex justify-center bg-gray-100/50">
                {loadError ? (
                    <div className="flex flex-col items-center justify-center gap-3 text-center p-8">
                        <AlertCircle className="w-10 h-10 text-red-400" />
                        <p className="text-sm text-gray-600 font-medium">PDFを読み込めませんでした</p>
                        <p className="text-xs text-gray-500 break-all max-w-xs">{loadError}</p>
                        <div className="flex flex-col gap-2 items-center mt-1">
                            <button
                                onClick={() => {
                                    setLoadError(null);
                                    setIsLoading(true);
                                    setBlobUrl(null);
                                    setRetryCount(c => c + 1);
                                }}
                                className="text-xs bg-blue-500 text-white px-3 py-1.5 rounded hover:bg-blue-600 transition-colors"
                            >
                                再試行
                            </button>
                            <a
                                href={url ?? '#'}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-blue-500 underline hover:text-blue-600"
                            >
                                別タブで直接開く
                            </a>
                        </div>
                    </div>
                ) : !blobUrl ? (
                    <div className="flex items-center justify-center w-[600px] min-h-[500px] bg-white rounded shadow-lg">
                        <div className="flex flex-col items-center gap-2 text-gray-400">
                            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                            <span className="text-xs">PDFを読み込み中...</span>
                        </div>
                    </div>
                ) : (
                    <div className="relative shadow-lg">
                        <Document
                            file={blobUrl}
                            onLoadSuccess={onDocumentLoadSuccess}
                            onLoadError={onDocumentLoadError}
                            loading={
                                <div className="flex items-center justify-center w-[600px] min-h-[500px] bg-white">
                                    <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                                </div>
                            }
                            className="bg-white min-h-[500px]"
                        >
                            <Page
                                pageNumber={pageNumber}
                                scale={scale}
                                renderTextLayer={false}
                                renderAnnotationLayer={false}
                                className="bg-white"
                                width={600}
                            />
                        </Document>
                    </div>
                )}
            </div>
        </div>
    );
}
