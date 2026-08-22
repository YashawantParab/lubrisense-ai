"use client";

import { useMemo } from "react";

import { SectionCard } from "@/components/section-card";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useFleetLatestConditions, useFleetLatestDecisions } from "@/hooks/use-intelligence";
import { READINESS_MODE_LABEL, readinessModeFor, type ReadinessMode } from "@/lib/action-readiness";

const MODE_ORDER: ReadinessMode[] = [
  "MONITORING_ONLY",
  "MANUAL_ACTION_REQUIRED",
  "HUMAN_APPROVAL_REQUIRED",
  "AUTO_ELIGIBLE_SIMULATION",
  "BLOCKED_INSUFFICIENT_EVIDENCE",
  "BLOCKED_SAFETY_INTERLOCK",
];

const MODE_BAR_CLASSES: Record<ReadinessMode, string> = {
  MONITORING_ONLY: "bg-emerald-500",
  MANUAL_ACTION_REQUIRED: "bg-amber-500",
  HUMAN_APPROVAL_REQUIRED: "bg-red-500",
  AUTO_ELIGIBLE_SIMULATION: "bg-sky-500",
  BLOCKED_INSUFFICIENT_EVIDENCE: "bg-zinc-300 dark:bg-zinc-600",
  BLOCKED_SAFETY_INTERLOCK: "bg-zinc-400 dark:bg-zinc-500",
};

function flattenMachines(hierarchy: ReturnType<typeof useHierarchy>["data"]) {
  const out: { id: string; status: string }[] = [];
  if (!hierarchy) return out;
  for (const customer of hierarchy.customers) {
    for (const site of customer.sites) {
      for (const plant of site.plants) {
        for (const line of plant.production_lines) {
          for (const machine of line.machines) {
            out.push({ id: machine.id, status: machine.status });
          }
        }
      }
    }
  }
  return out;
}

/** Second Overview chart (CLAUDE.md §6) — where the fleet sits between monitoring and a
 * closed-loop action right now. Every count derives from the same real condition/decision
 * data the Action Readiness page itself uses (`readinessModeFor`), never a separate
 * computation invented for this chart. */
export function ActionReadinessDistribution() {
  const hierarchy = useHierarchy();
  const conditions = useFleetLatestConditions();
  const decisions = useFleetLatestDecisions();

  const machineStatusById = useMemo(() => {
    const map = new Map<string, string>();
    for (const machine of flattenMachines(hierarchy.data)) {
      map.set(machine.id, machine.status);
    }
    return map;
  }, [hierarchy.data]);

  const decisionByMachine = useMemo(
    () => new Map((decisions.data ?? []).map((d) => [d.machine_id, d])),
    [decisions.data],
  );

  const counts = useMemo(() => {
    const tally = Object.fromEntries(MODE_ORDER.map((m) => [m, 0])) as Record<
      ReadinessMode,
      number
    >;
    for (const condition of conditions.data ?? []) {
      const status = machineStatusById.get(condition.machine_id);
      if (!status) continue;
      const decision = decisionByMachine.get(condition.machine_id) ?? null;
      tally[readinessModeFor(condition, decision, status)] += 1;
    }
    return tally;
  }, [conditions.data, decisionByMachine, machineStatusById]);

  const total = MODE_ORDER.reduce((sum, mode) => sum + counts[mode], 0);

  return (
    <SectionCard title="Action readiness">
      {total === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No condition assessments recorded yet.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
            {MODE_ORDER.filter((mode) => counts[mode] > 0).map((mode) => (
              <div
                key={mode}
                className={MODE_BAR_CLASSES[mode]}
                style={{ width: `${(counts[mode] / total) * 100}%` }}
                title={`${READINESS_MODE_LABEL[mode]}: ${counts[mode]}`}
              />
            ))}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
            {MODE_ORDER.filter((mode) => counts[mode] > 0).map((mode) => (
              <div key={mode} className="flex items-center gap-2 text-sm">
                <span className={`h-2 w-2 shrink-0 rounded-full ${MODE_BAR_CLASSES[mode]}`} />
                <dt className="text-zinc-500 dark:text-zinc-400">{READINESS_MODE_LABEL[mode]}</dt>
                <dd className="ml-auto font-medium text-zinc-900 dark:text-zinc-100">
                  {counts[mode]}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </SectionCard>
  );
}
