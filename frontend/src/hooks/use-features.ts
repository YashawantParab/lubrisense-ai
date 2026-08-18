"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getFeatureRegistry,
  getFeatureSets,
  getLatestMachineFeatures,
  listMachineFeatures,
} from "@/lib/api/features";

export function useFeatureSets() {
  return useQuery({ queryKey: ["features", "sets"], queryFn: getFeatureSets });
}

export function useFeatureRegistry() {
  return useQuery({ queryKey: ["features", "registry"], queryFn: getFeatureRegistry });
}

export function useLatestMachineFeatures(machineId: string, featureSet: string) {
  return useQuery({
    queryKey: ["features", "latest", machineId, featureSet],
    queryFn: () => getLatestMachineFeatures(machineId, featureSet),
    enabled: Boolean(machineId && featureSet),
    refetchInterval: 30_000,
  });
}

export function useMaterializedMachineFeatures(machineId: string, featureSet?: string) {
  return useQuery({
    queryKey: ["features", "materialized", machineId, featureSet],
    queryFn: () => listMachineFeatures(machineId, featureSet),
    enabled: Boolean(machineId),
  });
}
