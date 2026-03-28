export interface Issue {
  id: string;
  project_name: string;
  title: string;
  raw_input: string;
  category: '工程' | 'コスト' | '品質' | '安全';
  priority: 'critical' | 'normal' | 'minor';
  status: '発生中' | '対応中' | '解決済み';
  description: string | null;
  cause: string | null;
  impact: string | null;
  action_next: string | null;
  is_collapsed: 0 | 1;
  pos_x: number;
  pos_y: number;
  template_id: string | null;
  created_at: string;
  updated_at: string;
  assignee: string | null;
  context_memo: string | null;
}

export type EdgeRelationType = 'direct_cause' | 'indirect_cause' | 'correlation' | 'countermeasure';

export interface IssueEdge {
  id: string;
  from_id: string;
  to_id: string;
  confirmed: 0 | 1;
  label: string | null;
  relation_type: EdgeRelationType | null;
  created_at: string;
}

export interface IssueNote {
  id: string;
  issue_id: string;
  author: string | null;
  content: string;
  photo_path: string | null;
  created_at: string;
}

export interface AIInvestigationResult {
  type: 'rca' | 'impact' | 'countermeasure';
  result: string;
  related_issue_ids: string[];
}

export interface HealthCheckResult {
  orphans: Issue[];
  loops: string[][];
  unresolved_criticals: Issue[];
  ai_suggestions: { from_id: string; to_id: string; reason: string; confidence: number }[];
}

export interface InferredEdge {
  from_id: string;
  to_id: string;
  confidence: number;
  reason: string;
  suggested_label: string;
}

export interface CausalCandidate {
  issue_id: string;
  direction: 'cause_of_new' | 'result_of_new';
  confidence: number;
  reason: string;
}

export interface DuplicateCandidate {
  issue_id: string;
  similarity: number;
  reason: string;
}

export interface CaptureResponse {
  issue: Issue;
  causal_candidates: CausalCandidate[];
  duplicate_candidates: DuplicateCandidate[];
  ai_status?: 'analyzing' | 'done' | 'error';
}

export interface IssuesListResponse {
  issues: Issue[];
  edges: IssueEdge[];
  projects: string[];
}

export interface IssueCaptureData {
  issue: Issue;
  causal_candidates: CausalCandidate[];
  duplicate_candidates: DuplicateCandidate[];
}

export interface ProjectMember {
  id: string;
  project_name: string;
  name: string;
  role: string | null;
  created_at: string;
}

export interface DashboardSummary {
  total: number;
  status_counts: Record<string, number>;
  priority_counts: Record<string, number>;
  category_counts: Record<string, number>;
  assignee_counts: Record<string, number>;
  needs_action: Issue[];
  recent_issues: Issue[];
}

export interface BatchCaptureResponse {
  issues: Issue[];
  count: number;
}
