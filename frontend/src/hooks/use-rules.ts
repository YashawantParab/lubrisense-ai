"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getFinding,
  getFindings,
  getFindingsSummary,
  getMachineFindings,
  type RuleFindingsParams,
} from "@/lib/api/rules";

/** Polls every 15s — matches `useQualitySummary`/`useBaselineSummary`'s minimal developer/
 * product validation convention, not a final production-grade live view. */
export function useFindingsSummary() {
  return useQuery({
    queryKey: ["rules", "summary"],
    queryFn: () => getFindingsSummary(),
    refetchInterval: 15_000,
  });
}

export function useFindings(params: RuleFindingsParams = {}) {
  return useQuery({
    queryKey: ["rules", "findings", params],
    queryFn: () => getFindings(params),
    refetchInterval: 15_000,
  });
}

export function useMachineFindings(machineId: string) {
  return useQuery({
    queryKey: ["rules", "machine", machineId],
    queryFn: () => getMachineFindings(machineId),
    enabled: Boolean(machineId),
    refetchInterval: 15_000,
  });
}

export function useFinding(findingId: string) {
  return useQuery({
    queryKey: ["rules", "finding", findingId],
    queryFn: () => getFinding(findingId),
    enabled: Boolean(findingId),
  });
}
