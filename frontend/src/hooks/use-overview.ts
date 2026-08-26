"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import { getFleetOverview } from "@/lib/api/overview";

export function useFleetOverview() {
  return useAuthenticatedQuery({
    queryKey: ["fleet-overview"],
    queryFn: () => getFleetOverview(),
  });
}
