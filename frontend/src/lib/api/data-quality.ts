import { tenantScopedFetch } from "@/lib/api/client";
import type {
  MachineQualitySummaryResponse,
  QualityIssueResponse,
  SensorQualityDetailResponse,
  SensorQualityRecordResponse,
  TenantQualitySummaryResponse,
} from "@/lib/api/data-quality-types";

export interface QualityIssuesParams {
  severity?: string;
  status?: string;
  limit?: number;
}

export interface FleetSensorQualityParams {
  machine_id?: string;
  quality_state?: string;
  eligibility?: string;
  limit?: number;
}

function toQueryString(params: QualityIssuesParams | FleetSensorQualityParams): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function getQualitySummary(): Promise<TenantQualitySummaryResponse> {
  return tenantScopedFetch<TenantQualitySummaryResponse>("/api/v1/data-quality/summary");
}

export function getQualityIssues(
  params: QualityIssuesParams = {},
): Promise<QualityIssueResponse[]> {
  return tenantScopedFetch<QualityIssueResponse[]>(
    `/api/v1/data-quality/issues${toQueryString(params)}`,
  );
}

export function getSensorQuality(sensorId: string): Promise<SensorQualityDetailResponse> {
  return tenantScopedFetch<SensorQualityDetailResponse>(`/api/v1/data-quality/sensors/${sensorId}`);
}

/** Every sensor this tenant has evaluated at least once, including trusted sensors with
 * no active issue — the fleet-wide read model `GET /issues` alone cannot provide. */
export function getFleetSensorQuality(
  params: FleetSensorQualityParams = {},
): Promise<SensorQualityRecordResponse[]> {
  return tenantScopedFetch<SensorQualityRecordResponse[]>(
    `/api/v1/data-quality/sensors${toQueryString(params)}`,
  );
}

export function getMachineQuality(machineId: string): Promise<MachineQualitySummaryResponse> {
  return tenantScopedFetch<MachineQualitySummaryResponse>(
    `/api/v1/data-quality/machines/${machineId}`,
  );
}
