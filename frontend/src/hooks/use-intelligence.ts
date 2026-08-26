"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  getDecisionHistory,
  getFleetLatestConditions,
  getFleetLatestDecisions,
  getIntelligenceView,
} from "@/lib/api/intelligence";

export function useIntelligenceView(machineId: string) {
  return useAuthenticatedQuery({
    queryKey: ["intelligence", machineId],
    queryFn: () => getIntelligenceView(machineId),
    enabled: Boolean(machineId),
    retry: false,
  });
}

export function useFleetLatestConditions() {
  return useAuthenticatedQuery({
    queryKey: ["conditions", "fleet-latest"],
    queryFn: () => getFleetLatestConditions(),
  });
}

export function useFleetLatestDecisions() {
  return useAuthenticatedQuery({
    queryKey: ["decisions", "fleet-latest"],
    queryFn: () => getFleetLatestDecisions(),
  });
}

export function useDecisionHistory(machineId: string) {
  return useAuthenticatedQuery({
    queryKey: ["decisions", "history", machineId],
    queryFn: () => getDecisionHistory(machineId),
    enabled: Boolean(machineId),
    retry: false,
  });
}
