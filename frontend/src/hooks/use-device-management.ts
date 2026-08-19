"use client";

import { useQuery } from "@tanstack/react-query";

import { getMachineConfigurationChanges, getMachineDevices } from "@/lib/api/device-management";

export function useMachineDevices(machineId: string) {
  return useQuery({
    queryKey: ["device-management", "devices", machineId],
    queryFn: () => getMachineDevices(machineId),
    enabled: Boolean(machineId),
  });
}

export function useMachineConfigurationChanges(machineId: string) {
  return useQuery({
    queryKey: ["device-management", "changes", machineId],
    queryFn: () => getMachineConfigurationChanges(machineId),
    enabled: Boolean(machineId),
  });
}
