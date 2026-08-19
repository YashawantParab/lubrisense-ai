import { publicEnv } from "@/lib/env/public";
import type { ApiErrorResponse } from "@/lib/api/types";

export class ApiError extends Error {
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly correlationId: string | null;
  readonly status: number;

  constructor(status: number, body: ApiErrorResponse) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.correlationId = body.correlation_id;
  }
}

export interface ApiFetchOptions extends RequestInit {
  /** Overrides the default base URL — used by server components to reach the backend
   * via its internal network address instead of the browser-facing public URL. */
  baseUrl?: string;
}

/**
 * Typed fetch wrapper for the LubriSense backend. Every production-visible value shown
 * in the UI must be traceable to a real backend response (TECHNICAL_DECISIONS.md
 * ADR-008) — this client is the single place that boundary is crossed, so it is the
 * only place that should ever construct a backend URL or parse a backend response.
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { baseUrl = publicEnv.apiBaseUrl, ...init } = options;
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init.headers,
    },
  });

  if (!response.ok) {
    let body: ApiErrorResponse;
    try {
      body = (await response.json()) as ApiErrorResponse;
    } catch {
      body = {
        code: "UNKNOWN_ERROR",
        message: `Request to ${path} failed with status ${response.status}.`,
        details: {},
        correlation_id: response.headers.get("x-correlation-id"),
      };
    }
    throw new ApiError(response.status, body);
  }

  return (await response.json()) as T;
}

const TENANT_HEADER = "X-Tenant-ID";

/**
 * The current demo bearer token (Phase 24's `POST /auth/demo-login`), set by
 * `AuthProvider` (`@/lib/auth/context`) whenever the demo role switcher issues a new
 * token. Module-level rather than passed through every call site since almost every
 * request needs it — mirrors how `publicEnv.demoTenantId` is already used below. The
 * backend remains the actual authorization boundary in every case (Phase 24/29 — this
 * is presentation only, never relied on for security).
 */
let currentDemoToken: string | null = null;

export function setDemoAuthToken(token: string | null): void {
  currentDemoToken = token;
}

/**
 * Same as `apiFetch`, but attaches the dev-only demo tenant header (see
 * `publicEnv.demoTenantId`) required by every asset-hierarchy endpoint, plus the current
 * demo bearer token when one has been issued. Health/system endpoints don't need this
 * and should keep using `apiFetch` directly.
 */
export function tenantScopedFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  return apiFetch<T>(path, {
    ...options,
    headers: {
      [TENANT_HEADER]: publicEnv.demoTenantId,
      ...(currentDemoToken ? { Authorization: `Bearer ${currentDemoToken}` } : {}),
      ...options.headers,
    },
  });
}
