import type { CitationResponse } from "@/lib/api/knowledge-types";

export interface ToolCallResponse {
  tool_name: string;
  status: string;
  summary: string;
}

export interface DraftArtifactResponse {
  kind: string;
  content: Record<string, unknown>;
}

export interface AnswerSectionResponse {
  key: string;
  label: string;
  text: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  sections: AnswerSectionResponse[];
  evidence: string[];
  citations: CitationResponse[];
  tool_calls: ToolCallResponse[];
  draft_artifacts: DraftArtifactResponse[];
  limitations: string[];
  human_review_required: boolean;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  machine_id?: string;
  incident_id?: string;
  maintenance_case_id?: string;
}
