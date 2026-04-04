'use client';

import { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface Task {
  id: number;
  title: string;
  status: string;
  priority: string;
  due_date?: string | null;
  category_name?: string | null;
  category_color?: string | null;
}

const PRIORITY_DOT: Record<string, string> = {
  high: 'bg-red-500', medium: 'bg-blue-400', low: 'bg-gray-300',
};

interface TaskCalendarProps {
  tasks: Task[];
  onSelect: (id: number) => void;
}

export default function TaskCalendar({ tasks, onSelect }: TaskCalendarProps) {
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const days = useMemo(() => {
    const year = currentMonth.getFullYear(), month = currentMonth.getMonth();
    const firstDay = new Date(year, month, 1), lastDay = new Date(year, month + 1, 0);
    const startDay = new Date(firstDay); const dow = startDay.getDay() || 7;
    startDay.setDate(startDay.getDate() - (dow - 1));
    const endDay = new Date(lastDay); const edow = endDay.getDay() || 7;
    endDay.setDate(endDay.getDate() + (7 - edow));
    const r: Date[] = []; const d = new Date(startDay);
    while (d <= endDay) { r.push(new Date(d)); d.setDate(d.getDate() + 1); }
    return r;
  }, [currentMonth]);

  const tasksByDate = useMemo(() => {
    const m = new Map<string, Task[]>();
    for (const t of tasks) {
      if (!t.due_date || t.status === 'done') continue;
      (m.get(t.due_date) || (() => { const a: Task[] = []; m.set(t.due_date!, a); return a; })()).push(t);
    }
    return m;
  }, [tasks]);

  const today = new Date(); today.setHours(0, 0, 0, 0);
  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">{currentMonth.getFullYear()}年{currentMonth.getMonth() + 1}月</h2>
        <div className="flex items-center gap-1">
          <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))} className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100"><ChevronLeft size={18} /></button>
          <button onClick={() => setCurrentMonth(new Date())} className="px-3 py-1 rounded-lg text-xs text-gray-500 hover:bg-gray-100">今月</button>
          <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))} className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100"><ChevronRight size={18} /></button>
        </div>
      </div>
      <div className="grid grid-cols-7 gap-px mb-1">
        {['月','火','水','木','金','土','日'].map(d => <div key={d} className="text-center text-xs text-gray-400 py-2 font-medium">{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-px flex-1 bg-gray-100 rounded-lg overflow-hidden">
        {days.map(day => {
          const ds = day.toISOString().split('T')[0], dt = tasksByDate.get(ds) || [];
          return (
            <div key={ds} className={`bg-white p-1.5 min-h-[80px] flex flex-col ${day.getMonth() !== currentMonth.getMonth() ? 'opacity-40' : ''}`}>
              <span className={`text-xs mb-1 w-6 h-6 flex items-center justify-center rounded-full ${day.getTime() === today.getTime() ? 'bg-blue-600 text-white font-bold' : 'text-gray-500'}`}>{day.getDate()}</span>
              <div className="flex-1 space-y-0.5 overflow-hidden">
                {dt.slice(0, 3).map(t => (
                  <button key={t.id} onClick={() => onSelect(t.id)} className="w-full text-left text-[10px] px-1 py-0.5 rounded truncate hover:bg-gray-50 flex items-center gap-1">
                    <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${PRIORITY_DOT[t.priority] || PRIORITY_DOT.medium}`} />
                    <span className="text-gray-700 truncate">{t.title}</span>
                  </button>
                ))}
                {dt.length > 3 && <span className="text-[10px] text-gray-400 px-1">+{dt.length - 3}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
