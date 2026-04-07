// ===== タスク管理 共有型定義 =====

export interface Category {
  id: number;
  name: string;
  color: string;
}

export interface Comment {
  id: number;
  task_id: number;
  content: string;
  created_at: string;
}

export interface Reminder {
  id: number;
  task_id: number;
  remind_at: string;
  message?: string;
  is_sent: number;
}

export interface Label {
  id: number;
  name: string;
  color: string;
}

export interface Milestone {
  id: number;
  project_name: string;
  name: string;
  target_date?: string;
  status: string;
  sort_order: number;
}

export interface TaskDependency {
  id: number;
  predecessor_id: number;
  successor_id: number;
  dep_type: string;
  lag_days: number;
  task_title?: string;
  task_status?: string;
}

export interface Task {
  id: number;
  title: string;
  description?: string;
  status: 'todo' | 'in_progress' | 'done';
  priority: 'low' | 'medium' | 'high';
  category_id?: number;
  category_name?: string;
  category_color?: string;
  due_date?: string;
  start_date?: string;
  estimated_minutes?: number;
  actual_minutes?: number;
  project_name?: string;
  assignee_id?: string;
  assignee_name?: string;
  parent_id?: number;
  sort_order?: number;
  progress?: number;
  milestone_id?: number;
  milestone_name?: string;
  label_names?: string;
  label_colors?: string;
  label_ids?: string;
  created_at: string;
  updated_at: string;
  comments?: Comment[];
  reminders?: Reminder[];
  has_today_reminder?: number;
}

export interface ChatMessage {
  role: 'user' | 'ai';
  content: string;
}

export interface Meeting {
  id: number;
  title: string;
  project_name?: string;
  created_at: string;
}

export const PRIORITY_LABEL: Record<string, string> = { high: 'H', medium: 'M', low: 'L' };
export const PRIORITY_COLOR: Record<string, string> = {
  high: 'bg-gray-100 text-gray-600 border-gray-200',
  medium: 'bg-gray-100 text-gray-600 border-gray-200',
  low: 'bg-gray-100 text-gray-600 border-gray-200',
};
export const STATUS_LABEL: Record<string, string> = {
  todo: 'ToDo',
  in_progress: '進行中',
  done: '完了',
};
export const STATUS_HEADER_COLOR: Record<string, string> = {
  todo: 'bg-gray-100 text-gray-700',
  in_progress: 'bg-gray-100 text-gray-700',
  done: 'bg-gray-100 text-gray-700',
};

export function formatDate(iso?: string) {
  if (!iso) return '';
  return iso.slice(0, 10);
}
