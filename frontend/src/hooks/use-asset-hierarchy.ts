"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getHierarchy,
  getMachine,
  getMachineHierarchy,
  listSensors,
  type SensorListParams,
} from "@/lib/api/asset-hierarchy";

export function useHierarchy() {
  return useQuery({
    queryKey: ["asset-hierarchy", "hierarchy"],
    queryFn: () => getHierarchy(),
  });
}

export function useMachine(machineId: string) {
  return useQuery({
    queryKey: ["asset-hierarchy", "machine", machineId],
    queryFn: () => getMachine(machineId),
    enabled: Boolean(machineId),
  });
}

export function useMachineHierarchy(machineId: string) {
  return useQuery({
    queryKey: ["asset-hierarchy", "machine-hierarchy", machineId],
    queryFn: () => getMachineHierarchy(machineId),
    enabled: Boolean(machineId),
  });
}

export function useSensors(params: SensorListParams = {}) {
  return useQuery({
    queryKey: ["asset-hierarchy", "sensors", params],
    queryFn: () => listSensors(params),
  });
}
