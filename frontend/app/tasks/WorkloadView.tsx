'use client';

import React, { useState, useEffect } from 'react';
import { Loader2, Users } from 'lucide-react';
import { api } from './taskApi';

interface AssigneeWorkload {
  assignee_name: string;
  assignee_id: string;
  total: number;
  done: number;
  in_progress: number;
  todo: number;
  overdue: number;
}

export default function WorkloadView() {
  const [data, setData] = useState<AssigneeWorkload[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const result = await api.getWorkload();
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
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">担当者データがありません</p>
      </div>
    );
  }

  const maxTotal = Math.max(...data.map((d) => d.total), 1);

  return (
    <div className="max-w-4xl mx-auto">
      <div className="bg-white rounded-md border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">担当者別ワークロード</h3>
        </div>
        <div className="divide-y divide-gray-100">
          {data.map((d) => {
            const activeTotal = d.todo + d.in_progress;
            return (
              <div key={d.assignee_name} className="px-5 py-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-900">{d.assignee_name}</span>
                  <div className="flex gap-3 text-xs text-gray-500">
                    <span>残: {activeTotal}</span>
                    <span>完了: {d.done}</span>
                    {d.overdue > 0 && <span className="text-red-600 font-medium">超過: {d.overdue}</span>}
                  </div>
                </div>
                {/* Stacked bar */}
                <div className="w-full bg-gray-100 rounded-full h-3 flex overflow-hidden">
                  {d.done > 0 && (
                    <div className="bg-green-500 h-3 transition-all"
                      style={{ width: `${(d.done / maxTotal) * 100}%` }} title={`完了: ${d.done}`} />
                  )}
                  {d.in_progress > 0 && (
                    <div className="bg-blue-500 h-3 transition-all"
                      style={{ width: `${(d.in_progress / maxTotal) * 100}%` }} title={`進行中: ${d.in_progress}`} />
                  )}
                  {d.todo > 0 && (
                    <div className="bg-gray-300 h-3 transition-all"
                      style={{ width: `${(d.todo / maxTotal) * 100}%` }} title={`未着手: ${d.todo}`} />
                  )}
                  {d.overdue > 0 && (
                    <div className="bg-red-500 h-3 transition-all"
                      style={{ width: `${(d.overdue / maxTotal) * 100}%` }} title={`超過: ${d.overdue}`} />
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {/* Legend */}
        <div className="px-5 py-3 border-t border-gray-100 flex gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-green-500" />完了</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-blue-500" />進行中</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-gray-300" />未着手</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-red-500" />超過</span>
        </div>
      </div>
    </div>
  );
}
