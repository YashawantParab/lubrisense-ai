"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  getFeatureRegistry,
  getFeatureSets,
  getLatestMachineFeatures,
  listMachineFeatures,
} from "@/lib/api/features";

export function useFeatureSets() {
  return useAuthenticatedQuery({ queryKey: ["features", "sets"], queryFn: getFeatureSets });
}

export function useFeatureRegistry() {
  return useAuthenticatedQuery({ queryKey: ["features", "registry"], queryFn: getFeatureRegistry });
}

export function useLatestMachineFeatures(machineId: string, featureSet: string) {
  return useAuthenticatedQuery({
    queryKey: ["features", "latest", machineId, featureSet],
    queryFn: () => getLatestMachineFeatures(machineId, featureSet),
    enabled: Boolean(machineId && featureSet),
    refetchInterval: 30_000,
  });
}

export function useMaterializedMachineFeatures(machineId: string, featureSet?: string) {
  return useAuthenticatedQuery({
    queryKey: ["features", "materialized", machineId, featureSet],
    queryFn: () => listMachineFeatures(machineId, featureSet),
    enabled: Boolean(machineId),
  });
}
