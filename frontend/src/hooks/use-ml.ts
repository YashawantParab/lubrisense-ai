"use client";

import { useQuery } from "@tanstack/react-query";

import { getLatestMachineInference, getModel, getModels, listMachineInferenceHistory } from "@/lib/api/ml";

export function useModels() {
  return useQuery({ queryKey: ["ml", "models"], queryFn: getModels });
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
