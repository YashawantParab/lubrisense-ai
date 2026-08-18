import { tenantScopedFetch } from "@/lib/api/client";
import type {
  MachineFindingsResponse,
  RuleFindingResponse,
  TenantFindingSummaryResponse,
} from "@/lib/api/rules-types";

export interface RuleFindingsParams {
  machine_id?: string;
  finding_type?: string;
  severity?: string;
  state?: string;
  rule_id?: string;
  limit?: number;
}

export function getFindingsSummary(): Promise<TenantFindingSummaryResponse> {
  return tenantScopedFetch<TenantFindingSummaryResponse>("/api/v1/rules/summary");
}

export function getFindings(params: RuleFindingsParams = {}): Promise<RuleFindingResponse[]> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return tenantScopedFetch<RuleFindingResponse[]>(
    `/api/v1/rules/findings${query ? `?${query}` : ""}`,
  );
}

export function getMachineFindings(machineId: string): Promise<MachineFindingsResponse> {
  return tenantScopedFetch<MachineFindingsResponse>(`/api/v1/rules/machines/${machineId}`);
}

export function getFinding(findingId: string): Promise<RuleFindingResponse> {
  return tenantScopedFetch<RuleFindingResponse>(`/api/v1/rules/findings/${findingId}`);
}
