'use client';

import { useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { submitResearch } from '../lib/research-api';

interface Props {
  onSubmitted: (researchId: string) => void;
}

export default function ResearchForm({ onSubmitted }: Props) {
  const [question, setQuestion] = useState('');
  const [mode, setMode] = useState<'auto' | 'manual'>('auto');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await submitResearch(question.trim(), mode);
      onSubmitted(result.research_id);
      setQuestion('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'エラーが発生しました');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
      <h2 className="text-base font-semibold text-gray-800 mb-4 flex items-center gap-2">
        <Search className="w-4 h-4" />
        技術リサーチを依頼
      </h2>

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value.slice(0, 500))}
        placeholder="例: ケミカルアンカー 既存躯体接合の問題点と法令上の注意事項"
        rows={3}
        className="w-full resize-none rounded-xl border border-gray-200 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        disabled={loading}
      />
      <div className="text-xs text-gray-400 text-right mb-4">{question.length}/500</div>

      <div className="flex items-center gap-6 mb-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="radio"
            name="mode"
            value="auto"
            checked={mode === 'auto'}
            onChange={() => setMode('auto')}
            disabled={loading}
          />
          自動リサーチ（収集→レポートまで自動）
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="radio"
            name="mode"
            value="manual"
            checked={mode === 'manual'}
            onChange={() => setMode('manual')}
            disabled={loading}
          />
          プランのみ生成
        </label>
      </div>

      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      <button
        type="submit"
        disabled={loading || !question.trim()}
        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
        {loading ? '送信中...' : 'リサーチ開始'}
      </button>
    </form>
  );
}
