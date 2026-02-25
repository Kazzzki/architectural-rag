export interface ResearchGenerateRequest {
    node_id: string;
    node_label: string;
    node_phase: string;
    node_category: string;
    node_description: string;
    node_checklist: string[];
    node_deliverables: string[];
    selected_tools: string[];
    focus: string;
    extra_context?: string;
}

export interface KnowledgeItem {
    id: string;
    title: string;
    content: string;
    tags: string[];
}

export interface ResearchInjectRequest {
    node_id: string;
    node_label: string;
    node_phase: string;
    node_category: string;
    items: KnowledgeItem[];
}

export interface ParsedResearchResponse {
    gaps: string[];
    instructions: { tool: string; instruction: string }[];
    knowledgeItems: { title: string; tags: string[]; content: string }[];
}
