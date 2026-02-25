'use client';

import { useState, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, X, Loader2, AlertCircle, Download } from 'lucide-react';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { getAuthHeaders } from '@/lib/api';

// Worker setup: pdfjs-dist v5.x は .mjs 形式。CDN経由で確実に読み込む
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

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

    useEffect(() => {
        setPageNumber(Math.max(1, initialPage));
        setLoadError(null);
        setIsLoading(true);
    }, [initialPage, url]);

    function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
        setNumPages(numPages);
        setIsLoading(false);
        setLoadError(null);
        // 読み込み完了後、ページ番号が範囲内に収まるよう調整
        setPageNumber(prev => Math.max(1, Math.min(prev, numPages)));
    }

    function onDocumentLoadError(error: Error) {
        console.error('Error loading PDF:', error);
        setIsLoading(false);
        setLoadError(error.message || 'PDFの読み込みに失敗しました');
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

    // 認証ヘッダーを react-pdf の file prop に渡す
    const fileWithAuth = {
        url,
        httpHeaders: getAuthHeaders(),
        withCredentials: false,
    };

    return (
        <div className="flex flex-col h-full bg-gray-100 border-l border-gray-200 relative">
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200 shadow-sm z-10">
                <div className="flex items-center gap-4">
                    <span className="text-sm font-medium text-gray-700 truncate max-w-[200px]" title={url}>
                        {decodeURIComponent(url.split('/').pop()?.split('#')[0] || 'Document')}
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
                        <p className="text-xs text-gray-400 break-all max-w-xs">{loadError}</p>
                        <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-blue-500 underline hover:text-blue-600"
                        >
                            別タブで直接開く
                        </a>
                    </div>
                ) : (
                    <div className="relative shadow-lg">
                        <Document
                            file={fileWithAuth}
                            onLoadSuccess={onDocumentLoadSuccess}
                            onLoadError={onDocumentLoadError}
                            loading={
                                <div className="flex items-center justify-center w-[600px] min-h-[500px] bg-white">
                                    <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
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
