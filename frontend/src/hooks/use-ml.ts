"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getFleetLatestInference,
  getLatestMachineInference,
  getModel,
  getModels,
  listMachineInferenceHistory,
} from "@/lib/api/ml";

export function useModels() {
  return useQuery({ queryKey: ["ml", "models"], queryFn: getModels });
}

/** Read-only — never triggers inference. Powers the Fleet ML view / "what ML is
 * detecting now" summary from whatever has already been computed and persisted. */
export function useFleetLatestML() {
  return useQuery({ queryKey: ["ml", "fleet-latest"], queryFn: getFleetLatestInference });
}

export function useModel(modelId: string) {
  return useQuery({
    queryKey: ["ml", "model", modelId],
    queryFn: () => getModel(modelId),
    enabled: Boolean(modelId),
  });
}

export function useLatestMachineInference(machineId: string, modelId: string) {
  return useQuery({
    queryKey: ["ml", "latest", machineId, modelId],
    queryFn: () => getLatestMachineInference(machineId, modelId),
    enabled: Boolean(machineId && modelId),
    retry: false,
  });
}

export function useMachineInferenceHistory(machineId: string, modelId?: string) {
  return useQuery({
    queryKey: ["ml", "history", machineId, modelId],
    queryFn: () => listMachineInferenceHistory(machineId, modelId),
    enabled: Boolean(machineId),
  });
}
