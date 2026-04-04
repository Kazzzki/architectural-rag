'use client';

import React, { useState } from 'react';
import { X, Loader2, Copy, Check } from 'lucide-react';
import { api } from './taskApi';

export default function TaskReport({
  projects,
  onClose,
}: {
  projects: string[];
  onClose: () => void;
}) {
  const [period, setPeriod] = useState('weekly');
  const [projectName, setProjectName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    setError('');
    setReport('');
    try {
      const result = await api.generateReport({
        period,
        project_name: projectName || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });
      setReport(result.report ?? result.message ?? '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'レポート生成に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(report);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-md shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">AIステータスレポート</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-500">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">期間</label>
              <select value={period} onChange={(e) => setPeriod(e.target.value)}
                className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                <option value="weekly">週次</option>
                <option value="monthly">月次</option>
                <option value="custom">カスタム</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">プロジェクト</label>
              <select value={projectName} onChange={(e) => setProjectName(e.target.value)}
                className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm bg-white">
                <option value="">全PJ</option>
                {projects.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            {period === 'custom' && (
              <>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">開始日</label>
                  <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                    className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">終了日</label>
                  <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                    className="w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm" />
                </div>
              </>
            )}
          </div>

          <button onClick={handleGenerate} disabled={loading}
            className="w-full py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-700 disabled:opacity-50 flex items-center justify-center gap-2">
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" />生成中...</> : 'レポートを生成'}
          </button>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        {report && (
          <div className="flex-1 overflow-y-auto border-t border-gray-100">
            <div className="p-6">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-700">生成されたレポート</span>
                <button onClick={handleCopy}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded">
                  {copied ? <><Check className="w-3 h-3" />コピー済み</> : <><Copy className="w-3 h-3" />コピー</>}
                </button>
              </div>
              <div className="bg-gray-50 rounded-md p-4 text-sm text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">
                {report}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
