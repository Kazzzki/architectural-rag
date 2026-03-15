'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import { Copy, Trash2, ExternalLink } from 'lucide-react';
import { ResearchReport as ReportData, ResearchSource, deleteResearch } from '../lib/research-api';
import { useRouter } from 'next/navigation';

interface Props {
  report: ReportData;
}

function TrustBadge({ score }: { score: number | null }) {
  if (score == null) return null;
  const color = score >= 0.8 ? 'bg-green-100 text-green-700' : score >= 0.5 ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600';
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${color}`}>
      {(score * 100).toFixed(0)}%
    </span>
  );
}

function SourceCard({ source }: { source: ResearchSource }) {
  return (
    <div className="flex items-start justify-between gap-2 text-xs py-2 border-b border-gray-100 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-700 truncate">{source.title || source.url}</p>
        {source.summary && <p className="text-gray-500 mt-0.5 line-clamp-2">{source.summary}</p>}
        {source.url && (
          <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline flex items-center gap-1 mt-1">
            <ExternalLink className="w-3 h-3" />
            {source.url.slice(0, 60)}
          </a>
        )}
      </div>
      <TrustBadge score={source.trust_score} />
    </div>
  );
}

export default function ResearchReport({ report }: Props) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(report.report_markdown);
  };

  const handleDelete = async () => {
    if (!confirm('このレポートを削除しますか？')) return;
    setDeleting(true);
    try {
      await deleteResearch(report.research_id);
      router.push('/research');
    } catch {
      setDeleting(false);
    }
  };

  // カテゴリ別グルーピング
  const sourcesByCategory = report.sources.reduce<Record<string, ResearchSource[]>>((acc, s) => {
    const key = s.category || 'other';
    if (!acc[key]) acc[key] = [];
    acc[key].push(s);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {/* ヘッダー */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <h1 className="text-lg font-bold text-gray-900 mb-1">{report.question}</h1>
            <div className="flex items-center gap-3 text-xs text-gray-500">
              {report.domain && (
                <span className="bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full font-medium">
                  {report.domain}
                </span>
              )}
              {report.completed_at && (
                <span>{new Date(report.completed_at).toLocaleString('ja-JP')}</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleCopy} title="Markdownをコピー" className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors">
              <Copy className="w-4 h-4" />
            </button>
            <button onClick={handleDelete} disabled={deleting} title="削除" className="p-2 rounded-lg hover:bg-red-50 text-red-500 transition-colors disabled:opacity-50">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
        {report.summary && (
          <div className="mt-4 p-4 bg-gray-50 rounded-xl text-sm text-gray-700 leading-relaxed">
            {report.summary}
          </div>
        )}
      </div>

      {/* レポート本文 */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSanitize]}
            components={{
              p: ({ children }) => {
                const text = String(children);
                if (text.includes('⚠️')) {
                  return <p className="bg-orange-50 border-l-4 border-orange-400 pl-3 py-1 rounded-r">{children}</p>;
                }
                return <p>{children}</p>;
              },
            }}
          >
            {report.report_markdown}
          </ReactMarkdown>
        </div>
      </div>

      {/* 出典一覧 */}
      {report.sources.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-sm font-bold text-gray-700 mb-4">出典一覧</h2>
          {Object.entries(sourcesByCategory).map(([cat, sources]) => (
            <div key={cat} className="mb-4">
              <p className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-2">{cat}</p>
              {sources.map((s) => <SourceCard key={s.id} source={s} />)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
