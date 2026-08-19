"use client";

import { useQuery } from "@tanstack/react-query";

import { getFleetOverview } from "@/lib/api/overview";

export function useFleetOverview() {
  return useQuery({
    queryKey: ["fleet-overview"],
    queryFn: () => getFleetOverview(),
  });
}
