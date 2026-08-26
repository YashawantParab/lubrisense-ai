"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import { getLatestStateEstimates, listStateEstimateHistory } from "@/lib/api/state-estimation";

export function useLatestStateEstimates(machineId: string) {
  return useAuthenticatedQuery({
    queryKey: ["state-estimation", "latest", machineId],
    queryFn: () => getLatestStateEstimates(machineId),
    enabled: Boolean(machineId),
    retry: false,
  });
}

export function useStateEstimateHistory(machineId: string, stateType?: string) {
  return useAuthenticatedQuery({
    queryKey: ["state-estimation", "history", machineId, stateType],
    queryFn: () => listStateEstimateHistory(machineId, stateType),
    enabled: Boolean(machineId),
  });
}
