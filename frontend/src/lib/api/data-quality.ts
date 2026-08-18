import { tenantScopedFetch } from "@/lib/api/client";
import type {
  QualityIssueResponse,
  SensorQualityDetailResponse,
  TenantQualitySummaryResponse,
} from "@/lib/api/data-quality-types";

export interface QualityIssuesParams {
  severity?: string;
  status?: string;
  limit?: number;
}

export function getQualitySummary(): Promise<TenantQualitySummaryResponse> {
  return tenantScopedFetch<TenantQualitySummaryResponse>("/api/v1/data-quality/summary");
}

export function getQualityIssues(
  params: QualityIssuesParams = {},
): Promise<QualityIssueResponse[]> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return tenantScopedFetch<QualityIssueResponse[]>(
    `/api/v1/data-quality/issues${query ? `?${query}` : ""}`,
  );
}

export function getSensorQuality(sensorId: string): Promise<SensorQualityDetailResponse> {
  return tenantScopedFetch<SensorQualityDetailResponse>(`/api/v1/data-quality/sensors/${sensorId}`);
}
