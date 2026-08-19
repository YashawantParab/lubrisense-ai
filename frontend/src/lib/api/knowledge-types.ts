export interface KnowledgeDocumentResponse {
  id: string;
  tenant_id: string | null;
  document_key: string;
  title: string;
  document_type: string;
  version: string;
  status: string;
  source_name: string;
  effective_date: string | null;
  approved_at: string | null;
  approved_by: string | null;
  created_at: string;
}

export interface CitationResponse {
  document_id: string;
  document_title: string;
  document_version: string;
  document_type: string;
  section: string;
  heading: string;
  chunk_id: string;
}

export interface RetrievalResultResponse {
  citation: CitationResponse;
  excerpt: string;
  score: number;
}

export interface RAGAnswerResponse {
  status: string;
  text: string;
  citations: CitationResponse[];
  procedure_results: RetrievalResultResponse[];
  service_case_results: RetrievalResultResponse[];
}
