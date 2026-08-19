import { tenantScopedFetch } from "@/lib/api/client";
import type { IncidentEventResponse, IncidentResponse } from "@/lib/api/incidents-types";

export function listIncidents(params?: {
  machineId?: string;
  state?: string;
}): Promise<IncidentResponse[]> {
  const query = new URLSearchParams();
  if (params?.machineId) query.set("machine_id", params.machineId);
  if (params?.state) query.set("state", params.state);
  return tenantScopedFetch<IncidentResponse[]>(
    `/api/v1/incidents${query.size ? `?${query}` : ""}`,
  );
}

export function getIncident(incidentId: string): Promise<IncidentResponse> {
  return tenantScopedFetch<IncidentResponse>(`/api/v1/incidents/${incidentId}`);
}

export function getIncidentTimeline(incidentId: string): Promise<IncidentEventResponse[]> {
  return tenantScopedFetch<IncidentEventResponse[]>(`/api/v1/incidents/${incidentId}/timeline`);
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return tenantScopedFetch<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export function evaluateMachine(machineId: string): Promise<IncidentResponse | null> {
  return post<IncidentResponse | null>(`/api/v1/incidents/machines/${machineId}/evaluate`);
}

export function acknowledgeIncident(incidentId: string): Promise<IncidentResponse> {
  return post<IncidentResponse>(`/api/v1/incidents/${incidentId}/acknowledge`);
}

export function startInvestigation(incidentId: string): Promise<IncidentResponse> {
  return post<IncidentResponse>(`/api/v1/incidents/${incidentId}/start-investigation`);
}

export function resolveIncident(incidentId: string, reason: string): Promise<IncidentResponse> {
  return post<IncidentResponse>(`/api/v1/incidents/${incidentId}/resolve`, { reason });
}

export function closeIncident(incidentId: string): Promise<IncidentResponse> {
  return post<IncidentResponse>(`/api/v1/incidents/${incidentId}/close`);
}
