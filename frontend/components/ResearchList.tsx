'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Trash2, FileText } from 'lucide-react';
import { ResearchJob, deleteResearch } from '../lib/research-api';

interface Props {
  jobs: ResearchJob[];
  onDeleted: (id: string) => void;
  onSelectRunning?: (id: string) => void;
}

const STATUS_BADGE: Record<string, string> = {
  accepted: 'bg-gray-100 text-gray-600',
  phase1_planning: 'bg-blue-100 text-blue-700',
  phase2_collecting: 'bg-yellow-100 text-yellow-700',
  phase3_synthesis: 'bg-orange-100 text-orange-700',
  plan_ready: 'bg-purple-100 text-purple-700',
  completed: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
};

const STATUS_LABEL: Record<string, string> = {
  accepted: '受付',
  phase1_planning: 'プランニング',
  phase2_collecting: '収集中',
  phase3_synthesis: 'レポート生成',
  plan_ready: 'プラン完了',
  completed: '完了',
  error: 'エラー',
};

function formatRelative(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}時間前`;
  return `${Math.floor(diff / 86400)}日前`;
}

const RUNNING_STATUSES = new Set(['accepted', 'phase1_planning', 'phase2_collecting', 'phase3_synthesis']);

export default function ResearchList({ jobs, onDeleted, onSelectRunning }: Props) {
  const router = useRouter();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('削除しますか？')) return;
    setDeletingId(id);
    try {
      await deleteResearch(id);
      onDeleted(id);
    } finally {
      setDeletingId(null);
    }
  };

  if (jobs.length === 0) {
    return <p className="text-sm text-gray-400 text-center py-8">リサーチ履歴がありません</p>;
  }

  return (
    <div className="space-y-2">
      {jobs.map((job) => (
        <div
          key={job.research_id}
          onClick={() => {
            if (RUNNING_STATUSES.has(job.status) && onSelectRunning) {
              onSelectRunning(job.research_id);
            } else {
              router.push(`/research/${job.research_id}`);
            }
          }}
          className="flex items-center gap-4 bg-white rounded-xl border border-gray-200 p-4 cursor-pointer hover:bg-gray-50 transition-colors group"
        >
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800 truncate">
              {job.question.length > 40 ? job.question.slice(0, 40) + '...' : job.question}
            </p>
            <div className="flex items-center gap-3 mt-1">
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_BADGE[job.status] ?? 'bg-gray-100 text-gray-600'}`}>
                {STATUS_LABEL[job.status] ?? job.status}
              </span>
              <span className="text-xs text-gray-400">{job.sources_found}件</span>
              <span className="text-xs text-gray-400">{formatRelative(job.created_at)}</span>
            </div>
          </div>
          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => { e.stopPropagation(); router.push(`/research/${job.research_id}`); }}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
              title="詳細"
            >
              <FileText className="w-4 h-4" />
            </button>
            <button
              onClick={(e) => handleDelete(e, job.research_id)}
              disabled={deletingId === job.research_id}
              className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 disabled:opacity-50"
              title="削除"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
