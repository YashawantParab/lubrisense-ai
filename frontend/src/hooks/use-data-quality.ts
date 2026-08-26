"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  getFleetSensorQuality,
  getMachineQuality,
  getQualityIssues,
  getQualitySummary,
  getSensorQuality,
  type FleetSensorQualityParams,
  type QualityIssuesParams,
} from "@/lib/api/data-quality";

/** Polls every 15s — matches `useMachineTelemetry`'s minimal developer/product validation
 * convention (Phase 6), not a final production-grade live view. */
export function useQualitySummary() {
  return useAuthenticatedQuery({
    queryKey: ["data-quality", "summary"],
    queryFn: () => getQualitySummary(),
    refetchInterval: 15_000,
  });
}

export function useQualityIssues(params: QualityIssuesParams = {}) {
  return useAuthenticatedQuery({
    queryKey: ["data-quality", "issues", params],
    queryFn: () => getQualityIssues(params),
    refetchInterval: 15_000,
  });
}

export function useSensorQuality(sensorId: string) {
  return useAuthenticatedQuery({
    queryKey: ["data-quality", "sensor", sensorId],
    queryFn: () => getSensorQuality(sensorId),
    enabled: Boolean(sensorId),
    refetchInterval: 15_000,
  });
}

/** Every evaluated sensor fleet-wide, including trusted sensors with no active issue —
 * the read model the Data Quality page's main table is built on. */
export function useFleetSensorQuality(params: FleetSensorQualityParams = {}) {
  return useAuthenticatedQuery({
    queryKey: ["data-quality", "sensors", params],
    queryFn: () => getFleetSensorQuality(params),
    refetchInterval: 15_000,
  });
}

export function useMachineQuality(machineId: string) {
  return useAuthenticatedQuery({
    queryKey: ["data-quality", "machine", machineId],
    queryFn: () => getMachineQuality(machineId),
    enabled: Boolean(machineId),
    refetchInterval: 15_000,
  });
}
