import { tenantScopedFetch } from "@/lib/api/client";
import type {
  FeedbackRecordResponse,
  MaintenanceActionResponse,
  MaintenanceCaseResponse,
  TechnicianFindingResponse,
  WorkOrderResponse,
} from "@/lib/api/maintenance-types";

function post<T>(path: string, body?: unknown): Promise<T> {
  return tenantScopedFetch<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export function listCases(state?: string): Promise<MaintenanceCaseResponse[]> {
  const query = new URLSearchParams();
  if (state) query.set("state", state);
  return tenantScopedFetch<MaintenanceCaseResponse[]>(
    `/api/v1/maintenance/cases${query.size ? `?${query}` : ""}`,
  );
}

export function getCase(caseId: string): Promise<MaintenanceCaseResponse> {
  return tenantScopedFetch<MaintenanceCaseResponse>(`/api/v1/maintenance/cases/${caseId}`);
}

export function listFindings(caseId: string): Promise<TechnicianFindingResponse[]> {
  return tenantScopedFetch<TechnicianFindingResponse[]>(
    `/api/v1/maintenance/cases/${caseId}/findings`,
  );
}

export function listActions(caseId: string): Promise<MaintenanceActionResponse[]> {
  return tenantScopedFetch<MaintenanceActionResponse[]>(
    `/api/v1/maintenance/cases/${caseId}/actions`,
  );
}

export function getFeedback(caseId: string): Promise<FeedbackRecordResponse | null> {
  return tenantScopedFetch<FeedbackRecordResponse | null>(
    `/api/v1/maintenance/cases/${caseId}/feedback`,
  );
}

export function createCase(incidentId: string): Promise<MaintenanceCaseResponse> {
  return post<MaintenanceCaseResponse>("/api/v1/maintenance/cases", { incident_id: incidentId });
}

export function planCase(caseId: string): Promise<MaintenanceCaseResponse> {
  return post<MaintenanceCaseResponse>(`/api/v1/maintenance/cases/${caseId}/plan`);
}

export function startCase(caseId: string): Promise<MaintenanceCaseResponse> {
  return post<MaintenanceCaseResponse>(`/api/v1/maintenance/cases/${caseId}/start`);
}

export function recordFinding(
  caseId: string,
  body: { result: string; component?: string; observed_issue?: string; notes: string },
): Promise<TechnicianFindingResponse> {
  return post<TechnicianFindingResponse>(`/api/v1/maintenance/cases/${caseId}/finding`, body);
}

export function recordAction(
  caseId: string,
  body: { action_type: string; notes: string },
): Promise<MaintenanceActionResponse> {
  return post<MaintenanceActionResponse>(`/api/v1/maintenance/cases/${caseId}/action`, body);
}

export function completeCase(
  caseId: string,
  body: {
    classification: string;
    confirmed_component?: string;
    confirmed_finding?: string;
    notes?: string;
  },
): Promise<MaintenanceCaseResponse> {
  return post<MaintenanceCaseResponse>(`/api/v1/maintenance/cases/${caseId}/complete`, body);
}

export function createCmmsDraft(caseId: string): Promise<WorkOrderResponse> {
  return post<WorkOrderResponse>(`/api/v1/maintenance/cases/${caseId}/cmms-draft`);
}
