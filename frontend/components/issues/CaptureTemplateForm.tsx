'use client';

import React, { useState, useEffect } from 'react';
import { IssueTemplate, templateSelectionsToText } from '@/lib/issue_templates';
import { ChevronUp } from 'lucide-react';

interface CaptureTemplateFormProps {
  template: IssueTemplate;
  onComplete: (text: string) => void;
  onDismiss: () => void;
}

export default function CaptureTemplateForm({ template, onComplete, onDismiss }: CaptureTemplateFormProps) {
  const [selections, setSelections] = useState<Record<string, string>>({});

  // テンプレ変更時にリセット
  useEffect(() => {
    setSelections({});
  }, [template.id]);

  const allSelected = template.fields.every((f) => selections[f.id]);

  function handleSelect(fieldId: string, value: string) {
    const next = { ...selections, [fieldId]: value };
    setSelections(next);
    if (template.fields.every((f) => next[f.id])) {
      const text = templateSelectionsToText(template, next);
      onComplete(text);
    }
  }

  return (
    <div
      className="border border-blue-200 bg-blue-50 rounded-2xl p-4 space-y-3"
      style={{ animation: 'slideDown 0.2s ease-out' }}
    >
      <style>{`
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-blue-800">{template.label}</div>
        <button onClick={onDismiss} className="text-blue-400 hover:text-blue-700">
          <ChevronUp size={18} />
        </button>
      </div>

      {template.fields.map((field) => (
        <div key={field.id}>
          <div className="text-xs font-medium text-gray-600 mb-1">{field.label}</div>
          <div className="flex flex-wrap gap-2">
            {field.options.map((opt) => (
              <button
                key={opt}
                onClick={() => handleSelect(field.id, opt)}
                style={{ fontSize: 14 }}
                className={`px-3 py-2 rounded-xl border transition-all active:scale-95 ${
                  selections[field.id] === opt
                    ? 'bg-blue-600 text-white border-blue-600 font-medium'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-blue-50'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      ))}

      {allSelected && (
        <div className="text-xs text-green-700 bg-green-50 rounded-lg p-2">
          ✓ テキストエリアに入力しました。内容を確認して送信してください。
        </div>
      )}
    </div>
  );
}
