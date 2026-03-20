'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { Loader2, Sparkles } from 'lucide-react';

interface TriageSetupButtonProps {
  projectName: string;
  templateId: string;
}

export default function TriageSetupButton({ projectName, templateId }: TriageSetupButtonProps) {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch('/api/issues/triage-questions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: projectName, template_id: templateId }),
      });
      if (!res.ok) throw new Error(await res.text());
      setDone(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-green-600 font-medium">
        <Sparkles size={14} />
        トリアージ質問を生成しました
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <button
        onClick={handleGenerate}
        disabled={loading}
        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-violet-300 text-violet-600 hover:bg-violet-50 disabled:opacity-50 transition-colors"
      >
        {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
        トリアージ質問を生成
      </button>
      {error && <div className="text-xs text-red-500">{error}</div>}
    </div>
  );
}
