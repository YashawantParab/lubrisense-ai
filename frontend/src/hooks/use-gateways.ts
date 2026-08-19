"use client";

import { useQuery } from "@tanstack/react-query";

import { listGateways } from "@/lib/api/gateway";

export function useGateways(siteId?: string) {
  return useQuery({
    queryKey: ["gateways", siteId],
    queryFn: () => listGateways(siteId),
  });
}
