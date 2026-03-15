'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { ChevronDown } from 'lucide-react';

interface CaptureProjectSelectorProps {
  value: string;
  onChange: (project: string) => void;
}

export default function CaptureProjectSelector({ value, onChange }: CaptureProjectSelectorProps) {
  const [projects, setProjects] = useState<string[]>([]);

  useEffect(() => {
    authFetch('/api/issues/projects')
      .then((r) => r.json())
      .then((data) => setProjects(data.projects ?? []))
      .catch(() => {});
  }, []);

  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ fontSize: 16 }}
        className="w-full appearance-none border border-gray-300 rounded-xl px-4 py-3 pr-10 bg-white text-gray-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-400"
      >
        <option value="">プロジェクトを選択…</option>
        {projects.map((p) => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>
      <ChevronDown
        size={18}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
      />
    </div>
  );
}
