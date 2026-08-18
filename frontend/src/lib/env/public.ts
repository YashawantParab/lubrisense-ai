/**
 * Browser-safe environment configuration.
 *
 * Only `NEXT_PUBLIC_*` variables end up in the client bundle — Next.js inlines them at
 * build time. Nothing in this file may reference a non-prefixed environment variable;
 * server-only configuration lives in `./server.ts`, which is guarded so it cannot be
 * imported from client code at all (see `docs/ARCHITECTURE.md` §9, ADR-015 in
 * TECHNICAL_DECISIONS.md).
 */

export const publicEnv = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  appEnv: process.env.NEXT_PUBLIC_APP_ENV ?? "local",
  /**
   * Phase 2 has no authentication yet, so there is no session to derive a tenant from.
   * The backend requires an explicit `X-Tenant-ID` header on every asset-hierarchy
   * request (see backend/app/api/deps.py — DEVELOPMENT-ONLY, replaced by a real identity
   * claim once auth exists). The frontend's equivalent stand-in is this single
   * build-time tenant id, pointing at the deterministic demo tenant created by
   * `scripts/seed_demo_data.py`. Every real page will need a proper tenant-selection
   * flow once multi-tenant auth lands — see docs/ASSET_HIERARCHY.md.
   */
  demoTenantId: process.env.NEXT_PUBLIC_DEMO_TENANT_ID ?? "",
} as const;
