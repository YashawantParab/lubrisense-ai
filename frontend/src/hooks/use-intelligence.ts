"use client";

import { useQuery } from "@tanstack/react-query";

import { getIntelligenceView } from "@/lib/api/intelligence";

export function useIntelligenceView(machineId: string) {
  return useQuery({
    queryKey: ["intelligence", machineId],
    queryFn: () => getIntelligenceView(machineId),
    enabled: Boolean(machineId),
    retry: false,
  });
}
