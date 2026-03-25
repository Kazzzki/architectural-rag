'use client';

import React, { useState } from 'react';
import { authFetch } from '@/lib/api';
import { EdgeRelationType } from '@/lib/issue_types';
import { X } from 'lucide-react';

interface EdgeLabelEditorProps {
  edgeId: string;
  currentLabel: string | null;
  currentType: EdgeRelationType | null;
  x: number;
  y: number;
  onClose: () => void;
  onUpdated: () => void;
}

const RELATION_TYPES: { value: EdgeRelationType; label: string; color: string }[] = [
  { value: 'direct_cause', label: '直接原因', color: '#E24B4A' },
  { value: 'indirect_cause', label: '間接原因', color: '#F4A261' },
  { value: 'correlation', label: '相関', color: '#B4B2A9' },
  { value: 'countermeasure', label: '対策関係', color: '#52B788' },
];

export default function EdgeLabelEditor({
  edgeId, currentLabel, currentType, x, y, onClose, onUpdated,
}: EdgeLabelEditorProps) {
  const [label, setLabel] = useState(currentLabel || '');
  const [relationType, setRelationType] = useState<EdgeRelationType>(currentType || 'direct_cause');
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await authFetch(`/api/issues/edges/${edgeId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: label || null, relation_type: relationType }),
      });
      onUpdated();
    } finally {
      setSaving(false);
      onClose();
    }
  }

  return (
    <div
      className="fixed bg-white border border-gray-200 rounded-lg shadow-xl p-3 min-w-[220px] z-[100]"
      style={{ left: x, top: y }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-500">エッジ編集</span>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-0.5">
          <X size={14} />
        </button>
      </div>

      {/* 関係種別 */}
      <div className="mb-2">
        <label className="text-[10px] text-gray-400 block mb-1">関係種別</label>
        <div className="grid grid-cols-2 gap-1">
          {RELATION_TYPES.map((rt) => (
            <button
              key={rt.value}
              onClick={() => setRelationType(rt.value)}
              className={`text-xs px-2 py-1 rounded border transition-colors ${
                relationType === rt.value
                  ? 'border-blue-400 bg-blue-50 text-blue-700 font-medium'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              <span className="inline-block w-2 h-2 rounded-full mr-1" style={{ backgroundColor: rt.color }} />
              {rt.label}
            </button>
          ))}
        </div>
      </div>

      {/* ラベル */}
      <div className="mb-2">
        <label className="text-[10px] text-gray-400 block mb-1">ラベル（任意）</label>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="例: 雨天により"
          className="w-full text-sm border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
          maxLength={50}
        />
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full text-xs bg-blue-600 text-white rounded py-1.5 hover:bg-blue-700 disabled:opacity-40"
      >
        保存
      </button>
    </div>
  );
}
