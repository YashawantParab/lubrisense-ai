import { tenantScopedFetch } from "@/lib/api/client";
import type { PaginatedAuditEvents } from "@/lib/api/audit-types";

export function listAuditEvents(params?: {
  actorId?: string;
  entityType?: string;
  action?: string;
}): Promise<PaginatedAuditEvents> {
  const query = new URLSearchParams();
  if (params?.actorId) query.set("actor_id", params.actorId);
  if (params?.entityType) query.set("entity_type", params.entityType);
  if (params?.action) query.set("action", params.action);
  return tenantScopedFetch<PaginatedAuditEvents>(
    `/api/v1/audit-events${query.size ? `?${query}` : ""}`,
  );
}
