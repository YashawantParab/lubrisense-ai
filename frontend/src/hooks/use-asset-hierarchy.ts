"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  getHierarchy,
  getMachine,
  getMachineHierarchy,
  listSensors,
  type SensorListParams,
} from "@/lib/api/asset-hierarchy";

export function useHierarchy() {
  return useAuthenticatedQuery({
    queryKey: ["asset-hierarchy", "hierarchy"],
    queryFn: () => getHierarchy(),
  });
}

export function useMachine(machineId: string) {
  return useAuthenticatedQuery({
    queryKey: ["asset-hierarchy", "machine", machineId],
    queryFn: () => getMachine(machineId),
    enabled: Boolean(machineId),
  });
}

export function useMachineHierarchy(machineId: string) {
  return useAuthenticatedQuery({
    queryKey: ["asset-hierarchy", "machine-hierarchy", machineId],
    queryFn: () => getMachineHierarchy(machineId),
    enabled: Boolean(machineId),
  });
}

export function useSensors(params: SensorListParams = {}) {
  return useAuthenticatedQuery({
    queryKey: ["asset-hierarchy", "sensors", params],
    queryFn: () => listSensors(params),
  });
}
