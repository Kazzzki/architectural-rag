export interface PipelineNode {
    id: string;
    label: string;
    description: string;
    components: string[];
    domains: string[];
    default_doc_type: string;
    default_tools: string[];
}

export interface ResearchGenerateRequest {
    node_id: string;
    node_label: string;
    node_desc: string;
    node_components: string[];
    node_domains: string[];
    search_category: string;
    doc_type: string;
    selected_tools: string[];
    focus: string;
    extra_context?: string;
}

export interface KnowledgeItem {
    id: string;
    title: string;
    content: string;
    tags: string[];
    search_category: string;
    doc_type: string;
}

export interface ResearchInjectRequest {
    node_id: string;
    node_label: string;
    items: KnowledgeItem[];
}

export interface ParsedResearchResponse {
    gaps: string[];
    instructions: { tool: string; instruction: string }[];
    knowledgeItems: { title: string; tags: string[]; content: string }[];
}
