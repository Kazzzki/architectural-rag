'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import ResearchForm from '../../components/ResearchForm';
import ResearchStatus from '../../components/ResearchStatus';
import ResearchList from '../../components/ResearchList';
import { listResearches, ResearchJob } from '../../lib/research-api';

const STATUS_TABS = [
  { label: 'すべて', value: 'all' },
  { label: '実行中', value: 'phase2_collecting' },
  { label: '完了', value: 'completed' },
  { label: 'エラー', value: 'error' },
];

export default function ResearchPage() {
  const router = useRouter();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [tabStatus, setTabStatus] = useState('all');
  const [loading, setLoading] = useState(false);

  const RUNNING_STATUSES = new Set(['accepted', 'phase1_planning', 'phase2_collecting', 'phase3_synthesis']);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listResearches({ status: tabStatus });
      setJobs(data.items);
      // 実行中ジョブがあり、かつ進捗パネルが表示されていない場合は自動復元
      setActiveJobId((prev) => {
        if (prev) return prev;
        const running = data.items.find((j: ResearchJob) => RUNNING_STATUSES.has(j.status));
        return running ? running.research_id : null;
      });
    } catch {
      // サイレント
    } finally {
      setLoading(false);
    }
  }, [tabStatus]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const handleSubmitted = (researchId: string) => {
    setActiveJobId(researchId);
    fetchJobs();
  };

  const handleCompleted = () => {
    setActiveJobId(null);
    fetchJobs();
  };

  const handleDeleted = (id: string) => {
    setJobs((prev) => prev.filter((j) => j.research_id !== id));
  };

  const activeJob = jobs.find((j) => j.research_id === activeJobId);
  const isActiveJobRunning = activeJob
    ? !['completed', 'error', 'plan_ready'].includes(activeJob.status)
    : !!activeJobId;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push('/')}
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> チャットに戻る
          </button>
          <h1 className="text-xl font-bold text-gray-900">技術リサーチ</h1>
        </div>

        {/* 投入フォーム */}
        <ResearchForm onSubmitted={handleSubmitted} />

        {/* 実行中ジョブのステータス */}
        {activeJobId && isActiveJobRunning && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">実行中</p>
            <ResearchStatus researchId={activeJobId} onCompleted={handleCompleted} />
          </div>
        )}

        {/* ジョブ一覧 */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">履歴</p>
            <div className="flex gap-1">
              {STATUS_TABS.map((tab) => (
                <button
                  key={tab.value}
                  onClick={() => setTabStatus(tab.value)}
                  className={`text-xs px-3 py-1 rounded-full transition-colors ${
                    tabStatus === tab.value
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
          {loading ? (
            <p className="text-sm text-gray-400 text-center py-4">読み込み中...</p>
          ) : (
            <ResearchList jobs={jobs} onDeleted={handleDeleted} onSelectRunning={setActiveJobId} />
          )}
        </div>
      </div>
    </div>
  );
}
