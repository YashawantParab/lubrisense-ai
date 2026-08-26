"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  getBaselineSummary,
  getCurrentBaseline,
  getMachineBaselines,
  getSensorBaselines,
  type CurrentBaselineParams,
} from "@/lib/api/baselines";

/** Polls every 15s — matches `useQualitySummary`'s minimal developer/product validation
 * convention (Phase 7), not a final production-grade live view. */
export function useBaselineSummary() {
  return useAuthenticatedQuery({
    queryKey: ["baselines", "summary"],
    queryFn: () => getBaselineSummary(),
    refetchInterval: 15_000,
  });
}

export function useSensorBaselines(sensorId: string) {
  return useAuthenticatedQuery({
    queryKey: ["baselines", "sensor", sensorId],
    queryFn: () => getSensorBaselines(sensorId),
    enabled: Boolean(sensorId),
    refetchInterval: 15_000,
  });
}

export function useCurrentBaseline(sensorId: string, params: CurrentBaselineParams = {}) {
  return useAuthenticatedQuery({
    queryKey: ["baselines", "sensor", sensorId, "current", params],
    queryFn: () => getCurrentBaseline(sensorId, params),
    enabled: Boolean(sensorId),
  });
}

export function useMachineBaselines(machineId: string) {
  return useAuthenticatedQuery({
    queryKey: ["baselines", "machine", machineId],
    queryFn: () => getMachineBaselines(machineId),
    enabled: Boolean(machineId),
    refetchInterval: 15_000,
  });
}
