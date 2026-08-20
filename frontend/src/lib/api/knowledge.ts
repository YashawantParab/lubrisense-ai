import { tenantScopedFetch } from "@/lib/api/client";
import type { KnowledgeDocumentResponse, RAGAnswerResponse } from "@/lib/api/knowledge-types";

export function listDocuments(status?: string): Promise<KnowledgeDocumentResponse[]> {
  const query = new URLSearchParams();
  if (status) query.set("status", status);
  return tenantScopedFetch<KnowledgeDocumentResponse[]>(
    `/api/v1/knowledge/documents${query.size ? `?${query}` : ""}`,
  );
}

export function askKnowledge(query: string): Promise<RAGAnswerResponse> {
  return tenantScopedFetch<RAGAnswerResponse>("/api/v1/knowledge/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}
