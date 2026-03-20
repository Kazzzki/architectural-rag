'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { MessageSquare, CheckSquare, ClipboardList, FileAudio, Settings } from 'lucide-react';

const TABS = [
  { href: '/', icon: MessageSquare, label: 'チャット' },
  { href: '/tasks', icon: CheckSquare, label: 'タスク' },
  { href: '/issues', icon: ClipboardList, label: '課題' },
  { href: '/meetings', icon: FileAudio, label: '議事録' },
] as const;

export default function MobileTabBar() {
  const pathname = usePathname();

  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-50 bg-white/95 backdrop-blur border-t border-gray-200"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      <div className="flex items-center justify-around h-14">
        {TABS.map(({ href, icon: Icon, label }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex flex-col items-center justify-center gap-0.5 min-w-[56px] min-h-[44px] rounded-lg transition-colors ${
                active ? 'text-indigo-600' : 'text-gray-400'
              }`}
            >
              <Icon className="w-5 h-5" strokeWidth={active ? 2.5 : 2} />
              <span className={`text-[10px] ${active ? 'font-bold' : 'font-medium'}`}>{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
