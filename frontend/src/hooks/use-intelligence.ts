"use client";

import { useQuery } from "@tanstack/react-query";

import { getDecisionHistory, getIntelligenceView } from "@/lib/api/intelligence";

export function useIntelligenceView(machineId: string) {
  return useQuery({
    queryKey: ["intelligence", machineId],
    queryFn: () => getIntelligenceView(machineId),
    enabled: Boolean(machineId),
    retry: false,
  });
}

export function useDecisionHistory(machineId: string) {
  return useQuery({
    queryKey: ["decisions", "history", machineId],
    queryFn: () => getDecisionHistory(machineId),
    enabled: Boolean(machineId),
    retry: false,
  });
}
