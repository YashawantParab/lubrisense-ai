"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getQualityIssues,
  getQualitySummary,
  getSensorQuality,
  type QualityIssuesParams,
} from "@/lib/api/data-quality";

/** Polls every 15s — matches `useMachineTelemetry`'s minimal developer/product validation
 * convention (Phase 6), not a final production-grade live view. */
export function useQualitySummary() {
  return useQuery({
    queryKey: ["data-quality", "summary"],
    queryFn: () => getQualitySummary(),
    refetchInterval: 15_000,
  });
}

export function useQualityIssues(params: QualityIssuesParams = {}) {
  return useQuery({
    queryKey: ["data-quality", "issues", params],
    queryFn: () => getQualityIssues(params),
    refetchInterval: 15_000,
  });
}

export function useSensorQuality(sensorId: string) {
  return useQuery({
    queryKey: ["data-quality", "sensor", sensorId],
    queryFn: () => getSensorQuality(sensorId),
    enabled: Boolean(sensorId),
    refetchInterval: 15_000,
  });
}
