'use client';

import React, { useState, useEffect, useRef } from 'react';
import { authFetch } from '@/lib/api';
import { Issue } from '@/lib/issue_types';
import { X } from 'lucide-react';

interface MemoPopoverProps {
  issue: Issue;
  onClose: () => void;
  onUpdated: (updated: Issue) => void;
}

export default function MemoPopover({ issue, onClose, onUpdated }: MemoPopoverProps) {
  const [memo, setMemo] = useState(issue.context_memo || '');
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  async function handleSave() {
    if (memo === (issue.context_memo || '')) {
      onClose();
      return;
    }
    setSaving(true);
    try {
      const res = await authFetch(`/api/issues/${issue.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context_memo: memo }),
      });
      if (res.ok) {
        const updated: Issue = await res.json();
        onUpdated(updated);
      }
    } finally {
      setSaving(false);
      onClose();
    }
  }

  return (
    <div className="nodrag nopan absolute z-50 bg-white border border-yellow-300 rounded-lg shadow-lg p-3 min-w-[240px] max-w-[320px]"
      style={{ top: 0, left: '100%', marginLeft: 8 }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-500">メモ</span>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-0.5">
          <X size={14} />
        </button>
      </div>
      <textarea
        ref={textareaRef}
        value={memo}
        onChange={(e) => setMemo(e.target.value)}
        onBlur={handleSave}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onClose();
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSave();
        }}
        rows={4}
        placeholder="メモを入力... (Ctrl+Enterで保存)"
        className="w-full text-sm border border-gray-200 rounded px-2 py-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-yellow-400 bg-yellow-50/50"
        disabled={saving}
      />
      <div className="flex justify-end mt-1.5">
        <span className="text-[10px] text-gray-400">Ctrl+Enter で保存 / Esc で閉じる</span>
      </div>
    </div>
  );
}
