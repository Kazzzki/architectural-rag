import { authFetch } from '@/lib/api';
import type { Task, Label, Milestone, TaskDependency } from './types';

export async function apiFetch(path: string, opts?: RequestInit) {
  const res = await authFetch(path, {
    ...opts,
    signal: AbortSignal.timeout(30000),
    headers: { 'Content-Type': 'application/json', ...(opts?.headers ?? {}) },
  });
  if (res.status === 204) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Tasks CRUD
  getTasks: (filters: Record<string, string> = {}) => {
    const q = new URLSearchParams(filters).toString();
    return apiFetch(`/api/tasks${q ? `?${q}` : ''}`);
  },
  createTask: (data: Partial<Task>) =>
    apiFetch('/api/tasks', { method: 'POST', body: JSON.stringify(data) }),
  getTask: (id: number) => apiFetch(`/api/tasks/${id}`),
  updateTask: (id: number, data: Partial<Task>) =>
    apiFetch(`/api/tasks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTask: (id: number) =>
    apiFetch(`/api/tasks/${id}`, { method: 'DELETE' }),

  // Categories
  getCategories: () => apiFetch('/api/task-categories'),
  createCategory: (data: { name: string; color: string }) =>
    apiFetch('/api/task-categories', { method: 'POST', body: JSON.stringify(data) }),

  // Comments & Reminders
  addComment: (taskId: number, content: string) =>
    apiFetch(`/api/tasks/${taskId}/comments`, {
      method: 'POST', body: JSON.stringify({ content }),
    }),
  addReminder: (taskId: number, remind_at: string, message?: string) =>
    apiFetch(`/api/tasks/${taskId}/reminders`, {
      method: 'POST', body: JSON.stringify({ remind_at, message }),
    }),
  getPendingReminders: () => apiFetch('/api/tasks/reminders/pending'),

  // Projects
  getProjects: () => apiFetch('/api/issues/projects').then((d: { projects: string[] }) => d.projects ?? []),

  // AI Chat
  chat: (message: string) =>
    apiFetch('/api/tasks/chat', { method: 'POST', body: JSON.stringify({ message }) }),

  // Labels
  getLabels: () => apiFetch('/api/task-labels'),
  createLabel: (data: { name: string; color: string }) =>
    apiFetch('/api/task-labels', { method: 'POST', body: JSON.stringify(data) }),
  attachLabels: (taskId: number, label_ids: number[]) =>
    apiFetch(`/api/tasks/${taskId}/labels`, { method: 'POST', body: JSON.stringify({ label_ids }) }),
  detachLabel: (taskId: number, labelId: number) =>
    apiFetch(`/api/tasks/${taskId}/labels/${labelId}`, { method: 'DELETE' }),

  // Subtasks
  getSubtasks: (taskId: number) => apiFetch(`/api/tasks/${taskId}/subtasks`),

  // Bulk
  bulkUpdate: (data: { task_ids: number[]; status?: string; priority?: string; assignee_name?: string }) =>
    apiFetch('/api/tasks/bulk', { method: 'PUT', body: JSON.stringify(data) }),
  bulkCreate: (tasks: Partial<Task>[]) =>
    apiFetch('/api/tasks/bulk-create', { method: 'POST', body: JSON.stringify({ tasks }) }),

  // AI Features
  extractFromMeeting: (meetingId: number) =>
    apiFetch('/api/tasks/extract-from-meeting', { method: 'POST', body: JSON.stringify({ meeting_id: meetingId }) }),
  generateReport: (data: { period: string; project_name?: string; start_date?: string; end_date?: string }) =>
    apiFetch('/api/tasks/report/generate', { method: 'POST', body: JSON.stringify(data) }),

  // Milestones
  getMilestones: (projectName?: string) =>
    apiFetch(`/api/task-milestones${projectName ? `?project_name=${projectName}` : ''}`),
  createMilestone: (data: Partial<Milestone>) =>
    apiFetch('/api/task-milestones', { method: 'POST', body: JSON.stringify(data) }),
  updateMilestone: (id: number, data: Partial<Milestone>) =>
    apiFetch(`/api/task-milestones/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Portfolio & Workload
  getPortfolio: () => apiFetch('/api/tasks/portfolio'),
  getWorkload: (projectName?: string) =>
    apiFetch(`/api/tasks/workload${projectName ? `?project_name=${projectName}` : ''}`),

  // Recurrence
  setRecurrence: (taskId: number, data: { rrule_type: string; interval_value?: number; day_of_week?: string; day_of_month?: number }) =>
    apiFetch(`/api/tasks/${taskId}/recurrence`, { method: 'POST', body: JSON.stringify(data) }),
  deleteRecurrence: (taskId: number) =>
    apiFetch(`/api/tasks/${taskId}/recurrence`, { method: 'DELETE' }),

  // Dependencies
  getDependencies: (taskId: number) =>
    apiFetch(`/api/tasks/${taskId}/dependencies`) as Promise<{ predecessors: TaskDependency[]; successors: TaskDependency[] }>,
  addDependency: (taskId: number, data: { successor_id: number; dep_type?: string; lag_days?: number }) =>
    apiFetch(`/api/tasks/${taskId}/dependencies`, { method: 'POST', body: JSON.stringify(data) }),
  removeDependency: (taskId: number, depId: number) =>
    apiFetch(`/api/tasks/${taskId}/dependencies/${depId}`, { method: 'DELETE' }),

  // Meetings (for extraction)
  getMeetings: () => apiFetch('/api/meetings'),
};
