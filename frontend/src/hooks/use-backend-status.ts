"use client";

import { useQuery } from "@tanstack/react-query";

import { getReadiness, getSystemInfo } from "@/lib/api/backend";

const POLL_INTERVAL_MS = 10_000;

export function useBackendReadiness() {
  return useQuery({
    queryKey: ["backend", "readiness"],
    queryFn: () => getReadiness(),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useBackendSystemInfo() {
  return useQuery({
    queryKey: ["backend", "system-info"],
    queryFn: () => getSystemInfo(),
    refetchInterval: POLL_INTERVAL_MS,
  });
}
