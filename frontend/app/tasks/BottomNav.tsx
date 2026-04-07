'use client';

import React from 'react';
import { Sun, FolderOpen, Plus, Bell, Menu } from 'lucide-react';

type Tab = 'today' | 'projects' | 'add' | 'notifications' | 'more';

export default function BottomNav({
  activeTab,
  onTabChange,
  onAdd,
  onMoreOpen,
}: {
  activeTab: string;
  onTabChange: (tab: string) => void;
  onAdd: () => void;
  onMoreOpen: () => void;
}) {
  const tabs: { key: Tab; icon: typeof Sun; label: string }[] = [
    { key: 'today', icon: Sun, label: '今日' },
    { key: 'projects', icon: FolderOpen, label: 'PJ' },
    { key: 'add', icon: Plus, label: '' },
    { key: 'notifications', icon: Bell, label: '通知' },
    { key: 'more', icon: Menu, label: 'その他' },
  ];

  return (
    <nav className="fixed bottom-0 inset-x-0 z-50 md:hidden bg-white border-t border-gray-200 pb-[env(safe-area-inset-bottom)]">
      <div className="flex items-end justify-around px-2 pt-1 pb-1">
        {tabs.map(({ key, icon: Icon, label }) => {
          if (key === 'add') {
            return (
              <button key={key} onClick={onAdd} aria-label="タスクを追加"
                className="flex flex-col items-center -mt-4">
                <span className="w-12 h-12 rounded-full bg-gray-900 flex items-center justify-center shadow-lg">
                  <Plus className="w-6 h-6 text-white" />
                </span>
              </button>
            );
          }

          const isActive = key === 'today' ? activeTab === 'today' :
            key === 'projects' ? activeTab === 'portfolio' :
            key === 'notifications' ? false : false;

          return (
            <button key={key}
              onClick={() => {
                if (key === 'today') onTabChange('today');
                else if (key === 'projects') onTabChange('portfolio');
                else if (key === 'more') onMoreOpen();
              }}
              className="flex flex-col items-center py-1 px-3 min-w-[48px]">
              <Icon className={`w-5 h-5 ${isActive ? 'text-gray-900' : 'text-gray-400'}`} />
              <span className={`text-[10px] mt-0.5 ${isActive ? 'text-gray-900 font-medium' : 'text-gray-400'}`}>
                {label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
