"use client";

import { useMemo } from "react";

import { useIncidents } from "@/hooks/use-incidents";
import type { IncidentResponse } from "@/lib/api/incidents-types";

const SEVERITY_RANK: Record<string, number> = {
  CRITICAL: 3,
  HIGH: 2,
  WARNING: 1,
  INFO: 0,
};

function isOpen(incident: IncidentResponse): boolean {
  return incident.state !== "RESOLVED" && incident.state !== "CLOSED";
}

function compareByStory(a: IncidentResponse, b: IncidentResponse): number {
  const aOpen = isOpen(a);
  const bOpen = isOpen(b);
  if (aOpen !== bOpen) return aOpen ? -1 : 1; // an open incident always outranks a resolved one

  const aSeverity = SEVERITY_RANK[a.severity] ?? -1;
  const bSeverity = SEVERITY_RANK[b.severity] ?? -1;
  if (aSeverity !== bSeverity) return bSeverity - aSeverity;

  return new Date(b.first_detected_at).getTime() - new Date(a.first_detected_at).getTime();
}

/**
 * Identifies "the story that most deserves a reviewer's attention right now" from real,
 * persisted incident data — never a hardcoded machine id. An open incident always
 * outranks a resolved one (something needs attention now beats a past success story);
 * among incidents in the same open/resolved bucket, higher severity wins, then
 * most-recently-detected. On the seeded hosted demo this deterministically surfaces the
 * flagship machine's story (it is the only machine with real incident/decision/
 * maintenance evidence) without the frontend ever naming that machine directly — on a
 * fleet with a genuine live incident, it surfaces that instead, exactly as intended.
 */
export function usePriorityIncident() {
  const incidents = useIncidents();

  const priorityIncident = useMemo(() => {
    const rows = incidents.data ?? [];
    if (rows.length === 0) return null;
    return [...rows].sort(compareByStory)[0];
  }, [incidents.data]);

  return { ...incidents, priorityIncident };
}
