"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getDecisionHistory,
  getFleetLatestConditions,
  getFleetLatestDecisions,
  getIntelligenceView,
} from "@/lib/api/intelligence";

export function useIntelligenceView(machineId: string) {
  return useQuery({
    queryKey: ["intelligence", machineId],
    queryFn: () => getIntelligenceView(machineId),
    enabled: Boolean(machineId),
    retry: false,
  });
}

export function useFleetLatestConditions() {
  return useQuery({
    queryKey: ["conditions", "fleet-latest"],
    queryFn: () => getFleetLatestConditions(),
  });
}

export function useFleetLatestDecisions() {
  return useQuery({
    queryKey: ["decisions", "fleet-latest"],
    queryFn: () => getFleetLatestDecisions(),
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
