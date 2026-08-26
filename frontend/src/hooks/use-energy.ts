"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  getEnergyAssessmentHistory,
  getEnergyOutcomeHistory,
  getFleetLatestAttribution,
  getFleetLatestCarbon,
  getFleetLatestEnergyAssessment,
  getFleetLatestEnergyOutcome,
} from "@/lib/api/energy";

/**
 * Fleet-wide "latest" reads, filtered client-side by `machine_id` (mirrors the
 * established `useFleetLatestML` pattern already used on Machine Detail) — deliberately
 * NOT the backend's single-machine `.../latest` routes, which compute-and-persist a fresh
 * assessment on every GET. A page render must never have that side effect.
 */
export function useFleetLatestEnergyAssessment() {
  return useAuthenticatedQuery({
    queryKey: ["energy", "assessment", "fleet-latest"],
    queryFn: () => getFleetLatestEnergyAssessment(),
  });
}

export function useEnergyAssessmentHistory(machineId: string, limit = 200) {
  return useAuthenticatedQuery({
    queryKey: ["energy", "assessment", "history", machineId, limit],
    queryFn: () => getEnergyAssessmentHistory(machineId, limit),
    enabled: Boolean(machineId),
  });
}

export function useFleetLatestAttribution() {
  return useAuthenticatedQuery({
    queryKey: ["energy", "attribution", "fleet-latest"],
    queryFn: () => getFleetLatestAttribution(),
  });
}

export function useFleetLatestEnergyOutcome() {
  return useAuthenticatedQuery({
    queryKey: ["energy", "outcome", "fleet-latest"],
    queryFn: () => getFleetLatestEnergyOutcome(),
  });
}

export function useEnergyOutcomeHistory(machineId: string, limit = 50) {
  return useAuthenticatedQuery({
    queryKey: ["energy", "outcome", "history", machineId, limit],
    queryFn: () => getEnergyOutcomeHistory(machineId, limit),
    enabled: Boolean(machineId),
  });
}

export function useFleetLatestCarbon() {
  return useAuthenticatedQuery({
    queryKey: ["energy", "carbon", "fleet-latest"],
    queryFn: () => getFleetLatestCarbon(),
  });
}
