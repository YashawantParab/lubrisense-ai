import { tenantScopedFetch } from "@/lib/api/client";
import type {
  AddSensorRequest,
  AssignGatewayRequest,
  CommissioningSessionResponse,
  StartCommissioningRequest,
} from "@/lib/api/commissioning-types";
import type { SensorResponse } from "@/lib/api/asset-hierarchy-types";

function post<T>(path: string, body?: unknown): Promise<T> {
  return tenantScopedFetch<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export function listCommissioningSessions(): Promise<CommissioningSessionResponse[]> {
  return tenantScopedFetch<CommissioningSessionResponse[]>("/api/v1/commissioning/sessions");
}

export function getCommissioningSession(sessionId: string): Promise<CommissioningSessionResponse> {
  return tenantScopedFetch<CommissioningSessionResponse>(
    `/api/v1/commissioning/sessions/${sessionId}`,
  );
}

export function startCommissioning(
  body: StartCommissioningRequest,
): Promise<CommissioningSessionResponse> {
  return post("/api/v1/commissioning/sessions", body);
}

export function addCommissioningSensor(
  sessionId: string,
  body: AddSensorRequest,
): Promise<SensorResponse> {
  return post(`/api/v1/commissioning/sessions/${sessionId}/sensors`, body);
}

export function assignCommissioningGateway(
  sessionId: string,
  body: AssignGatewayRequest,
): Promise<CommissioningSessionResponse> {
  return post(`/api/v1/commissioning/sessions/${sessionId}/gateway`, body);
}

export function validateCommissioning(sessionId: string): Promise<CommissioningSessionResponse> {
  return post(`/api/v1/commissioning/sessions/${sessionId}/validate`);
}

export function completeCommissioning(sessionId: string): Promise<CommissioningSessionResponse> {
  return post(`/api/v1/commissioning/sessions/${sessionId}/complete`);
}
