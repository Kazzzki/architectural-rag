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
}

export interface IssueEdge {
  id: string;
  from_id: string;
  to_id: string;
  confirmed: 0 | 1;
  created_at: string;
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
}

export interface IssuesListResponse {
  issues: Issue[];
  edges: IssueEdge[];
  projects: string[];
}
