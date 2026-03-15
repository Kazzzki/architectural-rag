import { authFetch } from './api';

export interface ResearchJob {
  research_id: string;
  question: string;
  status: string;
  phase_current: number;
  phase_total: number;
  phase_name: string;
  progress_percent: number;
  detail: string | null;
  sources_found: number;
  domain: string | null;
  summary: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ResearchSource {
  id: number;
  research_id: string;
  title: string | null;
  url: string | null;
  source_type: string | null;
  trust_score: number | null;
  category: string | null;
  summary: string | null;
}

export interface ResearchPlan {
  domain: string;
  categories: {
    id: string;
    name: string;
    queries: string[];
    priority: number;
    trust_target: number;
  }[];
  estimated_sources: number;
  key_aspects: string[];
}

export interface ResearchStatus {
  research_id: string;
  status: string;
  phase: { current: number; total: number; name: string };
  progress_percent: number;
  detail: string | null;
  sources_found: number;
  started_at: string;
  updated_at: string;
  plan: ResearchPlan | null;
}

export interface ResearchReport {
  research_id: string;
  question: string;
  domain: string | null;
  summary: string | null;
  report_markdown: string;
  sources: ResearchSource[];
  plan: Record<string, unknown> | null;
  completed_at: string | null;
}

export async function submitResearch(question: string, mode: string) {
  const res = await authFetch('/api/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, mode }),
  });
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`);
  return res.json();
}

export async function getResearchStatus(id: string): Promise<ResearchStatus> {
  const res = await authFetch(`/api/research/${id}/status`);
  if (!res.ok) throw new Error(`Status fetch failed: ${res.status}`);
  return res.json();
}

export async function getResearchReport(id: string): Promise<ResearchReport> {
  const res = await authFetch(`/api/research/${id}/report`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail?.detail || `Report not ready: ${res.status}`);
  }
  return res.json();
}

export async function listResearches(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<{ items: ResearchJob[]; total: number }> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set('status', params.status);
  if (params?.limit != null) qs.set('limit', String(params.limit));
  if (params?.offset != null) qs.set('offset', String(params.offset));
  const res = await authFetch(`/api/research${qs.toString() ? '?' + qs.toString() : ''}`);
  if (!res.ok) throw new Error(`List fetch failed: ${res.status}`);
  return res.json();
}

export async function deleteResearch(id: string) {
  const res = await authFetch(`/api/research/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
  return res.json();
}
