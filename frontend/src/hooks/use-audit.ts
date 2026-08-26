"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import { listAuditEvents } from "@/lib/api/audit";

export function useAuditEvents(params?: {
  actorId?: string;
  entityType?: string;
  action?: string;
}) {
  return useAuthenticatedQuery({
    queryKey: ["audit-events", params],
    queryFn: () => listAuditEvents(params),
  });
}
