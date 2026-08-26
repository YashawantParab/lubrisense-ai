"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import { listGateways } from "@/lib/api/gateway";

export function useGateways(siteId?: string) {
  return useAuthenticatedQuery({
    queryKey: ["gateways", siteId],
    queryFn: () => listGateways(siteId),
  });
}
