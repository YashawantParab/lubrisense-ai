"use client";

import { useQuery } from "@tanstack/react-query";

import { listAuditEvents } from "@/lib/api/audit";

export function useAuditEvents(params?: {
  actorId?: string;
  entityType?: string;
  action?: string;
}) {
  return useQuery({
    queryKey: ["audit-events", params],
    queryFn: () => listAuditEvents(params),
  });
}
