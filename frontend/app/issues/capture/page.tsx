'use client';

import React, { useEffect, useRef, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, CaptureResponse, IssuesListResponse } from '@/lib/issue_types';
import { IssueTemplate } from '@/lib/issue_templates';
import CaptureTemplateGrid from '@/components/issues/CaptureTemplateGrid';
import CaptureTemplateForm from '@/components/issues/CaptureTemplateForm';
import CaptureTextInput from '@/components/issues/CaptureTextInput';
import CaptureCausalConfirm from '@/components/issues/CaptureCausalConfirm';
import { ArrowLeft, ClipboardList } from 'lucide-react';
import Link from 'next/link';

export default function CapturePage() {
  const [projectName, setProjectName] = useState('');
  const [text, setText] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<IssueTemplate | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // プロジェクト一覧（datalist 補完用）
  const [projects, setProjects] = useState<string[]>([]);

  // 既存 issues（因果確認・プロジェクト切替で使用）
  const [existingIssues, setExistingIssues] = useState<Issue[]>([]);

  // 登録後の因果確認
  const [pendingCausal, setPendingCausal] = useState<{
    newIssueId: string;
    candidates: CaptureResponse['causal_candidates'];
  } | null>(null);

  // トースト
  const [toast, setToast] = useState<string | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 3000);
  }

  // プロジェクト一覧を取得（datalist 補完用）
  useEffect(() => {
    authFetch('/api/issues/projects')
      .then((r) => r.json())
      .then((data) => setProjects(data.projects ?? []))
      .catch(() => {});
  }, []);

  // プロジェクト変更時に既存 issues を取得
  useEffect(() => {
    if (!projectName) { setExistingIssues([]); return; }
    authFetch(`/api/issues?project_name=${encodeURIComponent(projectName)}`)
      .then((r) => r.json())
      .then((data: IssuesListResponse) => setExistingIssues(data.issues ?? []))
      .catch(() => {});
  }, [projectName]);

  function handleTemplateSelect(tmpl: IssueTemplate) {
    if (selectedTemplate?.id === tmpl.id) {
      setSelectedTemplate(null);
    } else {
      setSelectedTemplate(tmpl);
    }
  }

  function handleTemplateComplete(naturalText: string) {
    setText(naturalText);
  }

  function pollAnalysis(issueId: string, attempt = 0) {
    if (attempt >= 20) return;
    setTimeout(async () => {
      try {
        const res = await authFetch(`/api/issues/${issueId}/analysis`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.ai_status === 'done') {
          setExistingIssues((prev) => prev.map((iss) => iss.id === issueId ? data.issue : iss));
          if (data.causal_candidates.length > 0) {
            setPendingCausal({ newIssueId: issueId, candidates: data.causal_candidates });
          }
        } else if (data.ai_status === 'analyzing') {
          pollAnalysis(issueId, attempt + 1);
        }
      } catch { /* ignore */ }
    }, 600);
  }

  async function handleSubmit() {
    if (!text.trim()) return;
    if (!projectName) {
      showToast('プロジェクトを選択してください');
      return;
    }
    setSubmitting(true);
    try {
      const res = await authFetch('/api/issues/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: text.trim(), project_name: projectName }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: CaptureResponse = await res.json();

      // 既存 issues に追加（仮タイトルで即時表示）
      setExistingIssues((prev) => [...prev, data.issue]);

      // リセット
      setText('');
      setSelectedTemplate(null);
      showToast('登録しました ✓');

      // バックグラウンドでAI分析完了をポーリング
      if (data.ai_status === 'analyzing') {
        pollAnalysis(data.issue.id);
      } else if (data.causal_candidates.length > 0) {
        setPendingCausal({ newIssueId: data.issue.id, candidates: data.causal_candidates });
      }
    } catch (e: any) {
      showToast(`エラー: ${e.message ?? '送信に失敗しました'}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="min-h-screen bg-gray-50"
      style={{ maxWidth: 480, margin: '0 auto', padding: '0 0 env(safe-area-inset-bottom)' }}
    >
      {/* ヘッダー */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-200 sticky top-0 z-10">
        <Link href="/issues" className="text-gray-400 hover:text-gray-700">
          <ArrowLeft size={18} />
        </Link>
        <ClipboardList size={20} className="text-blue-600" />
        <h1 className="text-base font-semibold text-gray-800">課題キャプチャ</h1>
      </div>

      <div className="p-4 space-y-5">
        {/* テンプレグリッド */}
        <CaptureTemplateGrid
          selectedId={selectedTemplate?.id ?? null}
          onSelect={handleTemplateSelect}
        />

        {/* テンプレフォーム（選択時展開） */}
        {selectedTemplate && (
          <CaptureTemplateForm
            template={selectedTemplate}
            onComplete={handleTemplateComplete}
            onDismiss={() => setSelectedTemplate(null)}
          />
        )}

        {/* 区切り */}
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <div className="flex-1 h-px bg-gray-200" />
          または
          <div className="flex-1 h-px bg-gray-200" />
        </div>

        {/* テキスト + 音声 + 送信 */}
        <CaptureTextInput
          value={text}
          onChange={setText}
          onSubmit={handleSubmit}
          submitting={submitting}
          projectName={projectName}
          onProjectChange={setProjectName}
          projects={projects}
        />

        {/* 因果確認ダイアログ */}
        {pendingCausal && (
          <CaptureCausalConfirm
            newIssueId={pendingCausal.newIssueId}
            candidates={pendingCausal.candidates}
            existingIssues={existingIssues}
            onDone={() => {
              setPendingCausal(null);
              showToast('登録しました ✓');
            }}
          />
        )}
      </div>

      {/* トースト */}
      {toast && (
        <div
          className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-gray-800 text-white text-sm rounded-full px-5 py-3 shadow-lg z-50"
          style={{ whiteSpace: 'nowrap' }}
        >
          {toast}
        </div>
      )}
    </div>
  );
}
