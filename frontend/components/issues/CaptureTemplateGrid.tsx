'use client';

import React from 'react';
import { ISSUE_TEMPLATES, IssueTemplate } from '@/lib/issue_templates';

interface CaptureTemplateGridProps {
  selectedId: string | null;
  onSelect: (template: IssueTemplate) => void;
}

const TEMPLATE_COLORS: Record<string, string> = {
  schedule_delay: '#DBEAFE',
  cost_increase:  '#FEE2E2',
  quality_issue:  '#D1FAE5',
  safety_event:   '#FEF3C7',
  design_change:  '#EDE9FE',
  client_response: '#F3F4F6',
};

export default function CaptureTemplateGrid({ selectedId, onSelect }: CaptureTemplateGridProps) {
  return (
    <div>
      <div className="text-xs font-medium text-gray-500 mb-2">テンプレから選ぶ</div>
      <div className="grid grid-cols-3 gap-2">
        {ISSUE_TEMPLATES.map((tmpl) => (
          <button
            key={tmpl.id}
            onClick={() => onSelect(tmpl)}
            style={{
              fontSize: 14,
              backgroundColor: selectedId === tmpl.id
                ? '#3B82F6'
                : TEMPLATE_COLORS[tmpl.id] ?? '#F9FAFB',
              color: selectedId === tmpl.id ? '#fff' : '#374151',
              border: selectedId === tmpl.id ? '2px solid #2563EB' : '1px solid #E5E7EB',
            }}
            className="rounded-xl py-3 px-2 font-medium transition-all active:scale-95 text-center"
          >
            {tmpl.label}
          </button>
        ))}
      </div>
    </div>
  );
}
