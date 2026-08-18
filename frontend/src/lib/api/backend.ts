import { apiFetch, type ApiFetchOptions } from "@/lib/api/client";
import type { LivenessResponse, ReadinessResponse, SystemInfoResponse } from "@/lib/api/types";

export function getHealth(options?: ApiFetchOptions): Promise<LivenessResponse> {
  return apiFetch<LivenessResponse>("/health", options);
}

export function getReadiness(options?: ApiFetchOptions): Promise<ReadinessResponse> {
  return apiFetch<ReadinessResponse>("/ready", options);
}

export function getSystemInfo(options?: ApiFetchOptions): Promise<SystemInfoResponse> {
  return apiFetch<SystemInfoResponse>("/api/v1/system/info", options);
}
