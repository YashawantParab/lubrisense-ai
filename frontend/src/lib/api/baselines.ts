import { tenantScopedFetch } from "@/lib/api/client";
import type {
  CurrentBaselineResponse,
  MachineBaselinesResponse,
  SensorBaselinesResponse,
  TenantBaselineSummaryResponse,
} from "@/lib/api/baselines-types";

export function getBaselineSummary(): Promise<TenantBaselineSummaryResponse> {
  return tenantScopedFetch<TenantBaselineSummaryResponse>("/api/v1/baselines/summary");
}

export function getSensorBaselines(sensorId: string): Promise<SensorBaselinesResponse> {
  return tenantScopedFetch<SensorBaselinesResponse>(`/api/v1/baselines/sensors/${sensorId}`);
}

export interface CurrentBaselineParams {
  operating_state?: string;
  cycle_phase?: string;
  value?: number;
}

export function getCurrentBaseline(
  sensorId: string,
  params: CurrentBaselineParams = {},
): Promise<CurrentBaselineResponse> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return tenantScopedFetch<CurrentBaselineResponse>(
    `/api/v1/baselines/sensors/${sensorId}/current${query ? `?${query}` : ""}`,
  );
}

export function getMachineBaselines(machineId: string): Promise<MachineBaselinesResponse> {
  return tenantScopedFetch<MachineBaselinesResponse>(`/api/v1/baselines/machines/${machineId}`);
}
