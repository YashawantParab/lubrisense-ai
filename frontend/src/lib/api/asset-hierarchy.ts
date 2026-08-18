import { tenantScopedFetch } from "@/lib/api/client";
import type {
  HierarchyResponse,
  MachineHierarchyResponse,
  MachineResponse,
  PaginatedResponse,
  SensorResponse,
} from "@/lib/api/asset-hierarchy-types";

export function getHierarchy(): Promise<HierarchyResponse> {
  return tenantScopedFetch<HierarchyResponse>("/api/v1/hierarchy");
}

export function getMachine(machineId: string): Promise<MachineResponse> {
  return tenantScopedFetch<MachineResponse>(`/api/v1/machines/${machineId}`);
}

export function getMachineHierarchy(machineId: string): Promise<MachineHierarchyResponse> {
  return tenantScopedFetch<MachineHierarchyResponse>(`/api/v1/machines/${machineId}/hierarchy`);
}

export interface SensorListParams {
  limit?: number;
  offset?: number;
  sensor_type?: string;
  status?: string;
}

export function listSensors(
  params: SensorListParams = {},
): Promise<PaginatedResponse<SensorResponse>> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return tenantScopedFetch<PaginatedResponse<SensorResponse>>(
    `/api/v1/sensors${query ? `?${query}` : ""}`,
  );
}
