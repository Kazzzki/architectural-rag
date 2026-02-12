'use client';

import { useState, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, X, Loader2 } from 'lucide-react';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

// Worker setup
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;

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

    useEffect(() => {
        setPageNumber(initialPage);
    }, [initialPage, url]);

    function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
        setNumPages(numPages);
        setIsLoading(false);
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

    return (
        <div className="flex flex-col h-full bg-gray-100 border-l border-gray-200 relative">
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200 shadow-sm z-10">
                <div className="flex items-center gap-4">
                    <span className="text-sm font-medium text-gray-700 truncate max-w-[200px]" title={url}>
                        {url.split('/').pop()?.split('#')[0] || 'Document'}
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

                <button
                    onClick={onClose}
                    className="p-1.5 hover:bg-red-50 text-gray-500 hover:text-red-500 rounded-lg transition-colors"
                >
                    <X className="w-5 h-5" />
                </button>
            </div>

            {/* Document Area */}
            <div className="flex-1 overflow-auto p-4 flex justify-center bg-gray-100/50">
                <div className="relative shadow-lg">
                    <Document
                        file={url}
                        onLoadSuccess={onDocumentLoadSuccess}
                        onLoadError={(error) => console.error('Error loading PDF:', error)}
                        loading={
                            <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-20">
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
                            width={600} // Base width, scale handles the rest
                        />
                    </Document>
                </div>
            </div>
        </div>
    );
}
