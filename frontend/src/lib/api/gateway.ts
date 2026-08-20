import { tenantScopedFetch } from "@/lib/api/client";
import type { GatewayResponse } from "@/lib/api/gateway-types";

export function listGateways(siteId?: string): Promise<GatewayResponse[]> {
  const query = new URLSearchParams();
  if (siteId) query.set("site_id", siteId);
  return tenantScopedFetch<GatewayResponse[]>(`/api/v1/gateways${query.size ? `?${query}` : ""}`);
}
