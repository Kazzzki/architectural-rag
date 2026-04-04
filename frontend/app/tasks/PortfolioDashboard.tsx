'use client';

import React, { useState, useEffect } from 'react';
import { Loader2, FolderOpen } from 'lucide-react';
import { api } from './taskApi';

interface ProjectSummary {
  project_name: string;
  total: number;
  done: number;
  in_progress: number;
  todo: number;
  overdue: number;
  completion_rate: number;
  earliest_due?: string;
  latest_due?: string;
}

export default function PortfolioDashboard() {
  const [data, setData] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const result = await api.getPortfolio();
        setData(result ?? []);
      } catch {
        setData([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>;
  }

  if (data.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <FolderOpen className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">プロジェクトデータがありません</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((p) => (
          <div key={p.project_name} className="bg-white rounded-md border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900 truncate">{p.project_name}</h3>
              <span className="text-xs text-gray-500">{p.total}件</span>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-gray-100 rounded-full h-2 mb-3">
              <div className="bg-gray-700 h-2 rounded-full transition-all"
                style={{ width: `${p.completion_rate}%` }} />
            </div>

            <div className="grid grid-cols-4 gap-2 text-center">
              <div>
                <p className="text-lg font-bold text-gray-900">{p.completion_rate}%</p>
                <p className="text-[10px] text-gray-400">完了率</p>
              </div>
              <div>
                <p className="text-lg font-bold text-green-600">{p.done}</p>
                <p className="text-[10px] text-gray-400">完了</p>
              </div>
              <div>
                <p className="text-lg font-bold text-blue-600">{p.in_progress}</p>
                <p className="text-[10px] text-gray-400">進行中</p>
              </div>
              <div>
                <p className={`text-lg font-bold ${p.overdue > 0 ? 'text-red-600' : 'text-gray-300'}`}>{p.overdue}</p>
                <p className="text-[10px] text-gray-400">超過</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
