import { tenantScopedFetch } from "@/lib/api/client";
import type { TelemetryReadingResponse } from "@/lib/api/telemetry-types";

export interface MachineTelemetryParams {
  limit?: number;
  measurement_type?: string;
}

export function getMachineTelemetry(
  machineId: string,
  params: MachineTelemetryParams = {},
): Promise<TelemetryReadingResponse[]> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return tenantScopedFetch<TelemetryReadingResponse[]>(
    `/api/v1/telemetry/machines/${machineId}${query ? `?${query}` : ""}`,
  );
}
