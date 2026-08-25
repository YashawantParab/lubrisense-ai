import { tenantScopedFetch } from "@/lib/api/client";
import type {
  AreaPerformance,
  AttentionAsset,
  OrganizationPerformance,
  RecentOutcome,
  SitePerformance,
} from "@/lib/api/performance-types";

export function getOrganizationPerformance(): Promise<OrganizationPerformance> {
  return tenantScopedFetch<OrganizationPerformance>("/api/v1/performance/organization");
}

export function listSitePerformance(): Promise<SitePerformance[]> {
  return tenantScopedFetch<SitePerformance[]>("/api/v1/performance/sites");
}

export function getSitePerformance(siteId: string): Promise<SitePerformance> {
  return tenantScopedFetch<SitePerformance>(`/api/v1/performance/sites/${siteId}`);
}

export function listAreaPerformance(): Promise<AreaPerformance[]> {
  return tenantScopedFetch<AreaPerformance[]>("/api/v1/performance/areas");
}

export function getAreaPerformance(areaKey: string): Promise<AreaPerformance> {
  return tenantScopedFetch<AreaPerformance>(
    `/api/v1/performance/areas/${encodeURIComponent(areaKey)}`,
  );
}

export function getAttentionQueue(limit = 50): Promise<AttentionAsset[]> {
  return tenantScopedFetch<AttentionAsset[]>(`/api/v1/performance/attention?limit=${limit}`);
}

export function getRecentOutcomes(limit = 20): Promise<RecentOutcome[]> {
  return tenantScopedFetch<RecentOutcome[]>(`/api/v1/performance/outcomes?limit=${limit}`);
}
