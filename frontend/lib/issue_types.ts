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
  deadline: string | null;
  context_memo: string | null;
  is_task: 0 | 1;
  completed_at: string | null;
  due_time: string | null;
  section_name: string | null;
  parent_id: string | null;
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

export interface IssueAttachment {
  id: string;
  issue_id: string;
  attachment_type: 'photo' | 'drawing' | 'report';
  file_path: string;
  thumbnail_path: string | null;
  caption: string | null;
  created_at: string;
}

export interface CausalSuggestion {
  title: string;
  description: string;
  confidence: number;
  reason: string;
}

export interface ProjectMember {
  id: string;
  project_name: string;
  name: string;
  role: string | null;
  created_at: string;
}
