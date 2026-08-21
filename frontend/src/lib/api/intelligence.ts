import { tenantScopedFetch } from "@/lib/api/client";
import type {
  ConditionAssessmentResponse,
  DecisionAssessmentResponse,
  IntelligenceViewResponse,
} from "@/lib/api/intelligence-types";

export function getIntelligenceView(machineId: string): Promise<IntelligenceViewResponse> {
  return tenantScopedFetch<IntelligenceViewResponse>(`/api/v1/intelligence/machines/${machineId}`);
}

/** Read-only latest condition assessment per machine, fleet-wide — never recomputes.
 * Powers the Overview attention queue / condition distribution and the Fleet condition
 * column without triggering N re-assessments on every page load. */
export function getFleetLatestConditions(): Promise<ConditionAssessmentResponse[]> {
  return tenantScopedFetch<ConditionAssessmentResponse[]>("/api/v1/conditions/fleet-latest");
}

export function getDecisionHistory(machineId: string): Promise<DecisionAssessmentResponse[]> {
  return tenantScopedFetch<DecisionAssessmentResponse[]>(
    `/api/v1/decisions/machines/${machineId}/history`,
  );
}

/** Read-only latest decision per machine, fleet-wide — never recomputes. Powers the
 * Overview attention queue's recommended-action column. */
export function getFleetLatestDecisions(): Promise<DecisionAssessmentResponse[]> {
  return tenantScopedFetch<DecisionAssessmentResponse[]>("/api/v1/decisions/fleet-latest");
}
