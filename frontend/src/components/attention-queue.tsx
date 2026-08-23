"use client";

import Link from "next/link";
import { useMemo } from "react";

import {
  ConfidenceBadge,
  IncidentStateBadge,
  PriorityBadge,
  SeverityBadge,
} from "@/components/badges";
import { EvidenceWhyDetails, evidenceBackingLine } from "@/components/condition-evidence";
import { EmptyState } from "@/components/empty-state";
import { SectionCard } from "@/components/section-card";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useIncidents } from "@/hooks/use-incidents";
import { useFleetLatestConditions, useFleetLatestDecisions } from "@/hooks/use-intelligence";
import { recommendedActionDisplay } from "@/lib/action-wording";
import { conditionInterpretation } from "@/lib/condition-interpretation";
import { componentFromName, equipmentTypeFor } from "@/lib/equipment";
import { fleetBucket, severityRank } from "@/lib/fleet-condition";
import { humanize } from "@/lib/terminology";
import type { HierarchyMachine } from "@/lib/api/asset-hierarchy-types";
import type { IncidentResponse } from "@/lib/api/incidents-types";

function flattenMachines(hierarchy: ReturnType<typeof useHierarchy>["data"]): HierarchyMachine[] {
  if (!hierarchy) return [];
  const out: HierarchyMachine[] = [];
  for (const customer of hierarchy.customers) {
    for (const site of customer.sites) {
      for (const plant of site.plants) {
        for (const line of plant.production_lines) {
          out.push(...line.machines);
        }
      }
    }
  }
  return out;
}

const OPEN_INCIDENT_STATES = new Set([
  "OPEN",
  "DETECTED",
  "ACKNOWLEDGED",
  "INVESTIGATING",
  "ACTION_PLANNED",
]);

/**
 * "ASSETS NEEDING ATTENTION" — the Overview's primary feature (CLAUDE.md §4). Joins the
 * three fleet-wide, read-only sources (latest condition, latest decision, incidents) by
 * machine_id entirely client-side — every field shown traces back to a real persisted
 * assessment/decision/incident, nothing here is computed or guessed in the frontend.
 */
export function AttentionQueue({ limit = 5 }: { limit?: number }) {
  const hierarchy = useHierarchy();
  const conditions = useFleetLatestConditions();
  const decisions = useFleetLatestDecisions();
  const incidents = useIncidents();

  const machines = useMemo(() => flattenMachines(hierarchy.data), [hierarchy.data]);
  const machineById = useMemo(() => new Map(machines.map((m) => [m.id, m])), [machines]);
  const decisionByMachine = useMemo(
    () => new Map((decisions.data ?? []).map((d) => [d.machine_id, d])),
    [decisions.data],
  );
  const openIncidentByMachine = useMemo(() => {
    const map = new Map<string, IncidentResponse>();
    for (const incident of incidents.data ?? []) {
      if (!OPEN_INCIDENT_STATES.has(incident.state)) continue;
      const existing = map.get(incident.machine_id);
      if (
        !existing ||
        new Date(incident.first_detected_at) > new Date(existing.first_detected_at)
      ) {
        map.set(incident.machine_id, incident);
      }
    }
    return map;
  }, [incidents.data]);

  const queue = useMemo(() => {
    return (conditions.data ?? [])
      .filter((c) => fleetBucket(c) === "attention")
      .filter((c) => machineById.has(c.machine_id))
      .sort((a, b) => severityRank(b.severity) - severityRank(a.severity))
      .slice(0, limit)
      .map((condition) => ({
        condition,
        machine: machineById.get(condition.machine_id)!,
        decision: decisionByMachine.get(condition.machine_id) ?? null,
        incident: openIncidentByMachine.get(condition.machine_id) ?? null,
      }));
  }, [conditions.data, machineById, decisionByMachine, openIncidentByMachine, limit]);

  if (conditions.isPending || hierarchy.isPending) {
    return (
      <SectionCard title="Assets needing attention">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading fleet condition…</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title="Assets needing attention"
      actions={
        <Link href="/fleet" className="text-xs text-sky-600 hover:underline dark:text-sky-400">
          View fleet
        </Link>
      }
    >
      {queue.length === 0 ? (
        <EmptyState
          title="Nothing needs attention right now"
          description="Every monitored asset with a real condition assessment currently reads healthy, recovering, or is limited by data quality/evidence — see the sections below."
        />
      ) : (
        <ul className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
          {queue.map(({ condition, machine, decision, incident }) => (
            <li key={condition.id} className="py-4 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <Link
                    href={`/machines/${machine.id}`}
                    className="text-base font-semibold text-sky-700 hover:underline dark:text-sky-400"
                  >
                    {machine.name}
                  </Link>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {machine.asset_code} ·{" "}
                    {equipmentTypeFor(machine.machine_type, machine.equipment_class)}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <SeverityBadge value={condition.severity} />
                  <ConfidenceBadge value={condition.confidence} />
                </div>
              </div>

              <p className="mt-2 text-sm font-medium text-zinc-800 dark:text-zinc-200">
                {humanize(condition.condition_type)}
              </p>
              <p className="mt-0.5 text-sm text-zinc-600 dark:text-zinc-400">
                {conditionInterpretation(condition.condition_type)}
              </p>
              <p className="mt-0.5 text-xs text-zinc-400 dark:text-zinc-600">
                {evidenceBackingLine(condition)}
              </p>
              <EvidenceWhyDetails why={condition.evidence_summary.why}>
                <p className="text-zinc-700 dark:text-zinc-300">
                  {condition.evidence_summary.what_is_happening}
                </p>
              </EvidenceWhyDetails>

              <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                <div>
                  <span className="text-xs text-zinc-400 dark:text-zinc-600">Recommended: </span>
                  {decision ? (
                    <span className="font-medium text-zinc-800 dark:text-zinc-200">
                      {recommendedActionDisplay(
                        decision.recommended_action,
                        componentFromName(machine.name),
                      )}
                    </span>
                  ) : (
                    <span className="text-zinc-500 dark:text-zinc-400">Not yet decided</span>
                  )}
                  {decision && <PriorityBadge value={decision.priority} />}
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-zinc-400 dark:text-zinc-600">Workflow: </span>
                  {incident ? (
                    <IncidentStateBadge value={incident.state} />
                  ) : (
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      Monitoring — no incident opened
                    </span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
