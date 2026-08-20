import { tenantScopedFetch } from "@/lib/api/client";
import type { DecisionAssessmentResponse, IntelligenceViewResponse } from "@/lib/api/intelligence-types";

export function getIntelligenceView(machineId: string): Promise<IntelligenceViewResponse> {
  return tenantScopedFetch<IntelligenceViewResponse>(
    `/api/v1/intelligence/machines/${machineId}`,
  );
}

export function getDecisionHistory(machineId: string): Promise<DecisionAssessmentResponse[]> {
  return tenantScopedFetch<DecisionAssessmentResponse[]>(
    `/api/v1/decisions/machines/${machineId}/history`,
  );
}
