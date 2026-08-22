/**
 * Types mirroring the backend's response contracts (backend/app/api/health.py,
 * backend/app/api/v1/system.py, backend/app/core/errors.py). Kept hand-written and
 * minimal for Phase 1; a generated client can replace this once the API surface grows
 * beyond platform-foundation endpoints.
 */

export interface DependencyStatus {
  name: string;
  healthy: boolean;
  required: boolean;
  status: "healthy" | "unhealthy" | "unavailable_optional";
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  dependencies: DependencyStatus[];
}

export interface LivenessResponse {
  status: string;
}

export interface SystemInfoResponse {
  application: string;
  version: string;
  environment: string;
}

export interface ApiErrorResponse {
  code: string;
  message: string;
  details: Record<string, unknown>;
  correlation_id: string | null;
}
