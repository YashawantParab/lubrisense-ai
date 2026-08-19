import { tenantScopedFetch } from "@/lib/api/client";
import type {
  LatestStateEstimatesResponse,
  StateEstimateResponse,
} from "@/lib/api/state-estimation-types";

export function getLatestStateEstimates(machineId: string): Promise<LatestStateEstimatesResponse> {
  return tenantScopedFetch<LatestStateEstimatesResponse>(
    `/api/v1/state-estimation/machines/${machineId}/latest`,
  );
}

export function listStateEstimateHistory(
  machineId: string,
  stateType?: string,
): Promise<StateEstimateResponse[]> {
  const query = new URLSearchParams();
  if (stateType) query.set("state_type", stateType);
  return tenantScopedFetch<StateEstimateResponse[]>(
    `/api/v1/state-estimation/machines/${machineId}/history${query.size ? `?${query}` : ""}`,
  );
}
