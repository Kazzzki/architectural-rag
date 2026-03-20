'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, CaptureResponse } from '@/lib/issue_types';
import { X, ChevronRight, Loader2 } from 'lucide-react';

interface TriageWizardProps {
  open: boolean;
  projectName: string;
  rawInput: string;
  onClose: () => void;
  onApplied: (resp: { issue: Issue; edges_created: { from_id: string; to_id: string }[] }) => void;
}

interface TriageQuestions {
  phase_question?: {
    label: string;
    options: { value: string; label: string; node_ids?: string[] }[];
  };
  category_question?: {
    label: string;
    options: { value: string; label: string; node_ids?: string[] }[];
  };
  node_questions?: {
    node_id: string;
    node_label: string;
    question: string;
    typical_assignee?: string;
  }[];
  assignee_question?: {
    label: string;
    options: string[];
  };
  related_issues_question?: {
    label: string;
    options: { id: string; title: string; category: string; status: string; assignee: string | null }[];
  };
}

type Step = 'loading' | 'phase' | 'category' | 'related' | 'assignee' | 'confirm';

export default function TriageWizard({ open, projectName, rawInput, onClose, onApplied }: TriageWizardProps) {
  const [questions, setQuestions] = useState<TriageQuestions | null>(null);
  const [step, setStep] = useState<Step>('loading');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Selections
  const [phaseValue, setPhaseValue] = useState<string>('');
  const [categoryValue, setCategoryValue] = useState<string>('');
  const [relatedIssueIds, setRelatedIssueIds] = useState<string[]>([]);
  const [assignee, setAssignee] = useState<string>('');

  useEffect(() => {
    if (!open) return;
    setStep('loading');
    setError(null);

    const params = new URLSearchParams({ project_name: projectName });
    if (rawInput) params.set('raw_input', rawInput);

    authFetch(`/api/issues/triage-questions?${params}`)
      .then(async (res) => {
        if (res.status === 404) {
          setError('トリアージ質問が未生成です。プロジェクト設定で「質問を生成」を先に実行してください。');
          return;
        }
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        setQuestions(data.questions);
        setStep('phase');
      })
      .catch((e) => setError(e.message));
  }, [open, projectName, rawInput]);

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const res = await authFetch('/api/issues/triage-apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_input: rawInput,
          project_name: projectName,
          phase_value: phaseValue || null,
          category_value: categoryValue || null,
          related_issue_ids: relatedIssueIds,
          assignee: assignee || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      onApplied(data);
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  function toggleRelated(id: string) {
    setRelatedIssueIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-[80]" onClick={onClose} />
      <div className="fixed inset-0 z-[81] flex items-center justify-center p-4">
        <div
          className="bg-white rounded-2xl shadow-2xl max-w-md w-full max-h-[80vh] flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h3 className="text-base font-semibold text-gray-800">課題トリアージ</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-700 p-1 rounded-lg hover:bg-gray-100">
              <X size={18} />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {step === 'loading' && !error && (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={24} className="animate-spin text-blue-500" />
                <span className="ml-2 text-sm text-gray-500">質問を読み込み中…</span>
              </div>
            )}

            {error && (
              <div className="text-sm text-red-600 bg-red-50 rounded-xl p-4">{error}</div>
            )}

            {/* Phase selection */}
            {step === 'phase' && questions?.phase_question && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-700">{questions.phase_question.label}</p>
                <div className="flex flex-wrap gap-2">
                  {questions.phase_question.options.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setPhaseValue(opt.value)}
                      className={`text-sm px-4 py-2 rounded-xl border transition-all ${
                        phaseValue === opt.value
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-gray-700 border-gray-300 hover:bg-blue-50'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Category selection */}
            {step === 'category' && questions?.category_question && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-700">{questions.category_question.label}</p>
                <div className="flex flex-wrap gap-2">
                  {questions.category_question.options.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setCategoryValue(opt.value)}
                      className={`text-sm px-4 py-2 rounded-xl border transition-all ${
                        categoryValue === opt.value
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-gray-700 border-gray-300 hover:bg-blue-50'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Related issues */}
            {step === 'related' && questions?.related_issues_question && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-700">{questions.related_issues_question.label}</p>
                {questions.related_issues_question.options.length === 0 ? (
                  <p className="text-xs text-gray-400">関連候補なし</p>
                ) : (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {questions.related_issues_question.options.map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => toggleRelated(opt.id)}
                        className={`w-full text-left text-sm px-3 py-2 rounded-lg border transition-all ${
                          relatedIssueIds.includes(opt.id)
                            ? 'bg-blue-50 border-blue-400'
                            : 'bg-white border-gray-200 hover:bg-gray-50'
                        }`}
                      >
                        <div className="font-medium text-gray-800">{opt.title}</div>
                        <div className="text-xs text-gray-400">{opt.category} · {opt.status}</div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Assignee */}
            {step === 'assignee' && questions?.assignee_question && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-700">{questions.assignee_question.label}</p>
                <div className="flex flex-wrap gap-2">
                  {questions.assignee_question.options.map((opt) => (
                    <button
                      key={opt}
                      onClick={() => setAssignee(opt)}
                      className={`text-sm px-4 py-2 rounded-xl border transition-all ${
                        assignee === opt
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-gray-700 border-gray-300 hover:bg-blue-50'
                      }`}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                  placeholder="または担当者名を入力"
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            )}

            {/* Confirm */}
            {step === 'confirm' && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-700">確認</p>
                <div className="text-sm bg-gray-50 rounded-xl p-3 space-y-1">
                  <div><span className="text-gray-500">課題:</span> {rawInput}</div>
                  {phaseValue && <div><span className="text-gray-500">フェーズ:</span> {phaseValue}</div>}
                  {categoryValue && <div><span className="text-gray-500">カテゴリ:</span> {categoryValue}</div>}
                  {relatedIssueIds.length > 0 && <div><span className="text-gray-500">関連課題:</span> {relatedIssueIds.length}件</div>}
                  {assignee && <div><span className="text-gray-500">担当者:</span> {assignee}</div>}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          {!error && step !== 'loading' && (
            <div className="px-5 py-4 border-t border-gray-100 flex justify-between">
              {step !== 'phase' ? (
                <button
                  onClick={() => {
                    const steps: Step[] = ['phase', 'category', 'related', 'assignee', 'confirm'];
                    const idx = steps.indexOf(step);
                    if (idx > 0) setStep(steps[idx - 1]);
                  }}
                  className="text-sm text-gray-600 hover:text-gray-800"
                >
                  戻る
                </button>
              ) : (
                <div />
              )}

              {step === 'confirm' ? (
                <button
                  onClick={handleSubmit}
                  disabled={submitting}
                  className="text-sm px-5 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
                >
                  {submitting ? <Loader2 size={14} className="animate-spin" /> : null}
                  登録する
                </button>
              ) : (
                <button
                  onClick={() => {
                    const steps: Step[] = ['phase', 'category', 'related', 'assignee', 'confirm'];
                    const idx = steps.indexOf(step);
                    if (idx < steps.length - 1) setStep(steps[idx + 1]);
                  }}
                  className="text-sm px-5 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 flex items-center gap-1"
                >
                  次へ <ChevronRight size={14} />
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
