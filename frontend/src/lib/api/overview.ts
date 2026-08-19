import { tenantScopedFetch } from "@/lib/api/client";
import type { FleetOverviewResponse } from "@/lib/api/overview-types";

export function getFleetOverview(): Promise<FleetOverviewResponse> {
  return tenantScopedFetch<FleetOverviewResponse>("/api/v1/fleet/overview");
}
