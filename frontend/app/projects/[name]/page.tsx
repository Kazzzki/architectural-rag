'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft, AlertTriangle, CheckCircle, Clock, Users,
  FileAudio, ClipboardList, Loader2, BarChart3,
} from 'lucide-react';
import { authFetch } from '@/lib/api';

interface DashboardData {
  project_name: string;
  total_issues: number;
  issue_stats: Record<string, number>;
  priority_stats: Record<string, number>;
  members: { id: string; name: string; role: string | null }[];
  meeting_count: number;
  recent_issues: { id: string; title: string; status: string; priority: string; category: string; created_at: string }[];
}

const STATUS_COLORS: Record<string, string> = {
  '発生中': 'bg-red-500',
  '対応中': 'bg-orange-400',
  '解決済み': 'bg-green-500',
};

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  normal: 'bg-blue-100 text-blue-700',
  minor: 'bg-gray-100 text-gray-500',
};

export default function ProjectDashboard() {
  const params = useParams();
  const projectName = decodeURIComponent(params.name as string);
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authFetch(`/api/projects/${encodeURIComponent(projectName)}/dashboard`)
      .then(r => r.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [projectName]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-gray-300" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">
        プロジェクトが見つかりません
      </div>
    );
  }

  const statusEntries = Object.entries(data.issue_stats);
  const totalBar = data.total_issues || 1;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center gap-4">
          <Link href="/issues" className="p-2 rounded-lg hover:bg-gray-100 text-gray-500">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{data.project_name}</h1>
            <p className="text-sm text-gray-500">プロジェクトダッシュボード</p>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-xs mb-1">
              <ClipboardList className="w-4 h-4" /> 課題数
            </div>
            <div className="text-2xl font-bold text-gray-900">{data.total_issues}</div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-xs mb-1">
              <AlertTriangle className="w-4 h-4" /> 発生中
            </div>
            <div className="text-2xl font-bold text-red-600">{data.issue_stats['発生中'] || 0}</div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-xs mb-1">
              <Users className="w-4 h-4" /> メンバー
            </div>
            <div className="text-2xl font-bold text-gray-900">{data.members.length}</div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 text-gray-500 text-xs mb-1">
              <FileAudio className="w-4 h-4" /> 議事録
            </div>
            <div className="text-2xl font-bold text-gray-900">{data.meeting_count}</div>
          </div>
        </div>

        {/* Status Bar */}
        {data.total_issues > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> ステータス内訳
            </h2>
            <div className="flex rounded-full overflow-hidden h-4 mb-3">
              {statusEntries.map(([status, count]) => (
                <div
                  key={status}
                  className={`${STATUS_COLORS[status] || 'bg-gray-300'}`}
                  style={{ width: `${(count / totalBar) * 100}%` }}
                  title={`${status}: ${count}件`}
                />
              ))}
            </div>
            <div className="flex gap-4 text-xs text-gray-500">
              {statusEntries.map(([status, count]) => (
                <span key={status} className="flex items-center gap-1">
                  <span className={`w-2 h-2 rounded-full ${STATUS_COLORS[status] || 'bg-gray-300'}`} />
                  {status} {count}件
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          {/* Members */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">チームメンバー</h2>
            {data.members.length === 0 ? (
              <p className="text-sm text-gray-400">メンバーが登録されていません</p>
            ) : (
              <div className="space-y-2">
                {data.members.map(m => (
                  <div key={m.id} className="flex items-center justify-between py-1">
                    <span className="text-sm text-gray-800">{m.name}</span>
                    {m.role && <span className="text-xs text-gray-400">{m.role}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Issues */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">最近の課題</h2>
            {data.recent_issues.length === 0 ? (
              <p className="text-sm text-gray-400">課題がありません</p>
            ) : (
              <div className="space-y-2">
                {data.recent_issues.map(issue => (
                  <div key={issue.id} className="flex items-center gap-2 py-1">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${PRIORITY_BADGE[issue.priority] || ''}`}>
                      {issue.priority === 'critical' ? '!!' : issue.priority === 'minor' ? '-' : ''}
                    </span>
                    <span className="text-sm text-gray-800 truncate flex-1">{issue.title}</span>
                    <span className="text-xs text-gray-400">{issue.status}</span>
                  </div>
                ))}
              </div>
            )}
            <Link
              href={`/issues?project=${encodeURIComponent(data.project_name)}`}
              className="block mt-3 text-xs text-indigo-600 hover:text-indigo-800"
            >
              全課題を見る →
            </Link>
          </div>
        </div>

        {/* Quick Links */}
        <div className="flex gap-3">
          <Link
            href={`/issues?project=${encodeURIComponent(data.project_name)}`}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            <ClipboardList className="w-4 h-4" /> 因果グラフを開く
          </Link>
          <Link
            href={`/meetings?project=${encodeURIComponent(data.project_name)}`}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50 transition-colors"
          >
            <FileAudio className="w-4 h-4" /> 議事録一覧
          </Link>
        </div>
      </main>
    </div>
  );
}
