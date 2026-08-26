"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import { getMachineTelemetry, type MachineTelemetryParams } from "@/lib/api/telemetry";

/** Polls every 10s — this is the minimal developer/product validation view (Phase 6 brief
 * §32), not the final Sensor Intelligence experience; a short poll interval is enough to
 * show the pipeline is actually flowing without building a websocket/SSE path yet. */
export function useMachineTelemetry(machineId: string, params: MachineTelemetryParams = {}) {
  return useAuthenticatedQuery({
    queryKey: ["telemetry", "machine", machineId, params],
    queryFn: () => getMachineTelemetry(machineId, params),
    enabled: Boolean(machineId),
    refetchInterval: 10_000,
  });
}
