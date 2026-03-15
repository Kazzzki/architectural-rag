'use client';

import { useEffect, useState } from 'react';
import { Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { getResearchStatus, ResearchStatus as StatusData, ResearchPlan } from '../lib/research-api';

interface Props {
  researchId: string;
  onCompleted?: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  phase1_planning: 'bg-blue-500',
  phase2_collecting: 'bg-yellow-500',
  phase3_synthesis: 'bg-orange-500',
  completed: 'bg-green-500',
  error: 'bg-red-500',
  plan_ready: 'bg-purple-500',
};

function formatElapsed(isoDate: string): string {
  const diff = Math.floor((Date.now() - new Date(isoDate).getTime()) / 1000);
  if (diff < 60) return `${diff}秒`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分`;
  return `${Math.floor(diff / 3600)}時間${Math.floor((diff % 3600) / 60)}分`;
}

function PlanView({ plan }: { plan: ResearchPlan }) {
  const [open, setOpen] = useState(false);
  const sorted = [...plan.categories].sort((a, b) => a.priority - b.priority);
  return (
    <div className="mt-4 border border-gray-100 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2 bg-gray-50 text-xs font-semibold text-gray-600 hover:bg-gray-100 transition-colors"
      >
        <span>リサーチプラン（ドメイン: {plan.domain}）</span>
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <div className="px-4 py-3 space-y-3 text-xs text-gray-700">
          {plan.key_aspects.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {plan.key_aspects.map((a, i) => (
                <span key={i} className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">{a}</span>
              ))}
            </div>
          )}
          <div className="space-y-2">
            {sorted.map((cat) => (
              <div key={cat.id} className="border border-gray-100 rounded-lg p-2">
                <div className="font-medium text-gray-800 mb-1">{cat.name}</div>
                <ul className="space-y-0.5">
                  {cat.queries.map((q, i) => (
                    <li key={i} className="text-gray-500 before:content-['›'] before:mr-1">{q}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="text-gray-400">想定ソース数: {plan.estimated_sources}件</p>
        </div>
      )}
    </div>
  );
}

export default function ResearchStatus({ researchId, onCompleted }: Props) {
  const [status, setStatus] = useState<StatusData | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval>;

    const poll = async () => {
      try {
        const data = await getResearchStatus(researchId);
        setStatus(data);
        if (data.status === 'completed' || data.status === 'error') {
          clearInterval(timer);
          onCompleted?.();
        }
      } catch {
        // ポーリング中のエラーはサイレントにスキップ
      }
    };

    poll();
    timer = setInterval(poll, 5000);
    return () => clearInterval(timer);
  }, [researchId, onCompleted]);

  if (!status) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 p-4">
        <Loader2 className="w-4 h-4 animate-spin" />
        読み込み中...
      </div>
    );
  }

  const barColor = STATUS_COLORS[status.status] ?? 'bg-gray-400';
  const isDone = status.status === 'completed' || status.status === 'error';

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-700">
          {status.phase.name || status.status}
        </span>
        <span className="text-xs text-gray-400">
          {isDone ? '完了' : `経過: ${formatElapsed(status.started_at)}`}
        </span>
      </div>

      {/* プログレスバー */}
      <div className="w-full bg-gray-100 rounded-full h-2 mb-3">
        <div
          className={`h-2 rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${status.progress_percent}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>{status.detail ?? ''}</span>
        <span>収集済み: {status.sources_found}件</span>
      </div>

      {status.status === 'error' && (
        <p className="mt-2 text-xs text-red-600">エラーが発生しました</p>
      )}

      {status.plan && <PlanView plan={status.plan} />}
    </div>
  );
}
