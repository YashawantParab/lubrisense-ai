import { tenantScopedFetch } from "@/lib/api/client";
import type {
  ConfigurationChangeResponse,
  ConfigurationSnapshotResponse,
} from "@/lib/api/device-management-types";

export function getMachineDevices(machineId: string): Promise<ConfigurationSnapshotResponse[]> {
  return tenantScopedFetch<ConfigurationSnapshotResponse[]>(
    `/api/v1/device-management/machines/${machineId}/devices`,
  );
}

export function getMachineConfigurationChanges(
  machineId: string,
): Promise<ConfigurationChangeResponse[]> {
  return tenantScopedFetch<ConfigurationChangeResponse[]>(
    `/api/v1/device-management/machines/${machineId}/changes`,
  );
}
