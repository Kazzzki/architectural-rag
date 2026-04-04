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
  legal_risk_level: 'high' | 'medium' | 'low' | null;
  evidence_status: 'recorded' | 'partial' | 'unrecorded' | null;
  evidence_gap?: boolean;
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
  type: 'rca' | 'impact' | 'countermeasure' | 'technical' | 'legal';
  result: string;
  related_issue_ids: string[];
  // D2 legal mode の拡張フィールド
  suggested_level?: 'high' | 'medium' | 'low';
  evidence_recommendations?: string[];
  sources?: { title: string; rel_path: string }[];
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

export interface RelatedStandard {
  standard_name: string;
  clause: string;
  key_values: string;
  relevance: string;
}

export interface ChainRiskScanResult {
  technical_risks: { issue_id: string; risk: string; severity: 'high' | 'medium' | 'low' }[];
  legal_risks: { issue_id: string; risk: string; law_reference: string }[];
  evidence_gaps: { issue_id: string; gap: string; urgency: 'high' | 'medium' | 'low' }[];
  recommended_actions: { action: string; priority: 'high' | 'medium' | 'low'; target_issue_ids: string[] }[];
  scanned_issue_ids: string[];
}
