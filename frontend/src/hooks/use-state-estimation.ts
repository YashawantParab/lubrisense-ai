"use client";

import { useQuery } from "@tanstack/react-query";

import { getLatestStateEstimates, listStateEstimateHistory } from "@/lib/api/state-estimation";

export function useLatestStateEstimates(machineId: string) {
  return useQuery({
    queryKey: ["state-estimation", "latest", machineId],
    queryFn: () => getLatestStateEstimates(machineId),
    enabled: Boolean(machineId),
    retry: false,
  });
}

export function useStateEstimateHistory(machineId: string, stateType?: string) {
  return useQuery({
    queryKey: ["state-estimation", "history", machineId, stateType],
    queryFn: () => listStateEstimateHistory(machineId, stateType),
    enabled: Boolean(machineId),
  });
}
