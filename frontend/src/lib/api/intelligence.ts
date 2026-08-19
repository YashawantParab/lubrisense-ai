import { tenantScopedFetch } from "@/lib/api/client";
import type { IntelligenceViewResponse } from "@/lib/api/intelligence-types";

export function getIntelligenceView(machineId: string): Promise<IntelligenceViewResponse> {
  return tenantScopedFetch<IntelligenceViewResponse>(
    `/api/v1/intelligence/machines/${machineId}`,
  );
}
