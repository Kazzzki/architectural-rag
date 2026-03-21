'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '@/lib/api';
import { X, FileText, File, Loader2, Search, ChevronRight } from 'lucide-react';

// ===== 型定義 =====

interface Document {
  id: number;
  filename: string;
  file_path: string;
  file_type: string;
  file_size: number;
  category: string;
  subcategory: string;
  doc_type: string | null;
  status: string;
  total_pages: number;
  created_at: string | null;
  updated_at: string | null;
}

interface DocumentDetail extends Document {
  content: string | null;
  file_url: string;
}

// ===== ユーティリティ =====

function formatBytes(bytes: number): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function fileTypeLabel(type: string): string {
  const map: Record<string, string> = {
    pdf: 'PDF',
    md: 'Markdown',
    txt: 'テキスト',
    png: '画像',
    jpg: '画像',
    jpeg: '画像',
  };
  return map[type] ?? type.toUpperCase();
}

function statusBadge(status: string) {
  const styles: Record<string, string> = {
    completed: 'bg-green-100 text-green-700',
    processing: 'bg-yellow-100 text-yellow-700',
    failed: 'bg-red-100 text-red-700',
    unprocessed: 'bg-gray-100 text-gray-500',
  };
  const labels: Record<string, string> = {
    completed: '完了',
    processing: '処理中',
    failed: 'エラー',
    unprocessed: '未処理',
  };
  const cls = styles[status] ?? 'bg-gray-100 text-gray-500';
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${cls}`}>
      {labels[status] ?? status}
    </span>
  );
}

// ===== プレビューパネル =====

function DocumentPreviewPanel({
  docId,
  onClose,
}: {
  docId: number;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const loadDetail = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch(`/api/documents/${docId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: DocumentDetail = await res.json();
      setDetail(data);
    } catch (err) {
      console.error('Failed to load document detail:', err);
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    loadDetail();
    return () => {
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
    };
  }, [loadDetail]);

  useEffect(() => {
    if (!detail || detail.file_type !== 'pdf') return;

    let revoked = false;
    setPdfLoading(true);
    (async () => {
      try {
        const res = await authFetch(`/api/documents/${docId}/file`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        if (!revoked) {
          const url = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
          setPdfBlobUrl(url);
        }
      } catch (err) {
        console.error('Failed to load PDF:', err);
      } finally {
        if (!revoked) setPdfLoading(false);
      }
    })();

    return () => {
      revoked = true;
      setPdfBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [detail, docId]);

  return (
    <div className="w-full md:w-[520px] flex-shrink-0 h-full border-l border-gray-200 bg-white flex flex-col">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 flex-shrink-0">
        <h3 className="text-sm font-semibold text-gray-700 truncate pr-4">
          {detail?.filename ?? 'ドキュメントプレビュー'}
        </h3>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 transition-colors flex-shrink-0"
          title="閉じる"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : !detail ? (
        <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
          読み込みエラー
        </div>
      ) : (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* メタ情報 */}
          <div className="px-5 py-3 border-b border-gray-100 flex-shrink-0 space-y-1 text-xs text-gray-500">
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <span>種別: <span className="text-gray-700">{fileTypeLabel(detail.file_type)}</span></span>
              {detail.total_pages > 0 && (
                <span>ページ数: <span className="text-gray-700">{detail.total_pages}p</span></span>
              )}
              <span>サイズ: <span className="text-gray-700">{formatBytes(detail.file_size)}</span></span>
              <span>登録日: <span className="text-gray-700">{formatDate(detail.created_at)}</span></span>
            </div>
            {detail.category && (
              <div className="text-gray-400">
                {detail.category}{detail.subcategory ? ` / ${detail.subcategory}` : ''}
              </div>
            )}
          </div>

          {/* プレビュー本体 */}
          {detail.file_type === 'pdf' ? (
            <div className="flex-1 relative bg-gray-100">
              {pdfLoading ? (
                <div className="absolute inset-0 flex items-center justify-center text-gray-400">
                  <Loader2 className="w-6 h-6 animate-spin" />
                </div>
              ) : pdfBlobUrl ? (
                <iframe
                  src={`${pdfBlobUrl}#toolbar=1`}
                  className="w-full h-full border-0"
                  title={detail.filename}
                />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center text-gray-400 text-sm">
                  PDFを読み込めませんでした
                </div>
              )}
            </div>
          ) : detail.content ? (
            <div className="flex-1 overflow-y-auto px-5 py-4">
              <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono leading-relaxed break-words">
                {detail.content}
              </pre>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
              プレビューできません
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ===== ドキュメント一覧行 =====

function DocumentRow({
  doc,
  selected,
  onClick,
}: {
  doc: Document;
  selected: boolean;
  onClick: () => void;
}) {
  const isPdf = doc.file_type === 'pdf';
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 border-b border-gray-100 flex items-center gap-3 transition-colors hover:bg-gray-50 ${
        selected ? 'bg-gray-100' : ''
      }`}
    >
      <div className="flex-shrink-0 text-gray-400">
        {isPdf ? <File className="w-4 h-4 text-red-400" /> : <FileText className="w-4 h-4 text-blue-400" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-800 truncate">{doc.filename}</span>
          {statusBadge(doc.status)}
        </div>
        <div className="text-xs text-gray-400 mt-0.5 flex gap-2">
          {doc.category && <span className="truncate">{doc.category}</span>}
          <span>{formatDate(doc.created_at)}</span>
          {doc.total_pages > 0 && <span>{doc.total_pages}p</span>}
        </div>
      </div>
      <ChevronRight className={`w-4 h-4 flex-shrink-0 transition-colors ${selected ? 'text-gray-600' : 'text-gray-300'}`} />
    </button>
  );
}

// ===== メインページ =====

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterCategory, setFilterCategory] = useState('');

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filterType) params.set('file_type', filterType);
      if (filterCategory) params.set('category', filterCategory);
      const res = await authFetch(`/api/documents?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDocuments(data.documents ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [filterType, filterCategory]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const filtered = documents.filter((d) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      d.filename.toLowerCase().includes(q) ||
      d.category.toLowerCase().includes(q) ||
      (d.doc_type ?? '').toLowerCase().includes(q)
    );
  });

  const categories = Array.from(new Set(documents.map((d) => d.category).filter(Boolean))).sort();

  return (
    <div className="flex flex-col h-screen bg-white overflow-hidden">
      {/* ヘッダー */}
      <header className="flex-shrink-0 border-b border-gray-200 px-6 py-4">
        <div className="flex items-center gap-4 flex-wrap">
          <h1 className="text-base font-semibold text-gray-800">ナレッジファイル</h1>

          {/* 検索 */}
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ファイル名・カテゴリで絞り込み..."
              className="w-full pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-300 bg-gray-50"
            />
          </div>

          {/* フィルター */}
          <div className="flex gap-2">
            <select
              value={filterType}
              onChange={(e) => { setFilterType(e.target.value); setSelectedId(null); }}
              className="px-2 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-gray-300"
            >
              <option value="">全ファイル種別</option>
              <option value="pdf">PDF</option>
              <option value="md">Markdown</option>
              <option value="txt">テキスト</option>
            </select>
            <select
              value={filterCategory}
              onChange={(e) => { setFilterCategory(e.target.value); setSelectedId(null); }}
              className="px-2 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-gray-300"
            >
              <option value="">全カテゴリ</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <span className="text-xs text-gray-400 ml-auto">
            {filtered.length} 件
          </span>
        </div>
      </header>

      {/* メインエリア */}
      <div className="flex-1 flex overflow-hidden">
        {/* リスト */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center items-center h-64">
              <Loader2 className="w-7 h-7 animate-spin text-gray-300" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-64 gap-3">
              <p className="text-red-400 text-sm">{error}</p>
              <button
                onClick={loadDocuments}
                className="text-xs text-blue-500 underline"
              >
                再試行
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
              ファイルが見つかりません
            </div>
          ) : (
            <div>
              {filtered.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  doc={doc}
                  selected={selectedId === doc.id}
                  onClick={() => setSelectedId(selectedId === doc.id ? null : doc.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* プレビューパネル */}
        {selectedId !== null && (
          <DocumentPreviewPanel
            docId={selectedId}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>
    </div>
  );
}
