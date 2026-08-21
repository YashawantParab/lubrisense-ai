"use client";

import Link from "next/link";
import { useMemo } from "react";

import { ConfidenceBadge, PriorityBadge, SeverityBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useFleetLatestConditions, useFleetLatestDecisions } from "@/hooks/use-intelligence";
import { fleetBucket } from "@/lib/fleet-condition";
import { humanize } from "@/lib/terminology";
import type { Tone } from "@/lib/terminology";
import type { DecisionAssessmentResponse } from "@/lib/api/intelligence-types";

type ReadinessMode =
  | "MONITORING_ONLY"
  | "MANUAL_ACTION_REQUIRED"
  | "HUMAN_APPROVAL_REQUIRED"
  | "BLOCKED_INSUFFICIENT_EVIDENCE";

const MODE_LABEL: Record<ReadinessMode, string> = {
  MONITORING_ONLY: "Monitoring only",
  MANUAL_ACTION_REQUIRED: "Manual action required",
  HUMAN_APPROVAL_REQUIRED: "Human approval required",
  BLOCKED_INSUFFICIENT_EVIDENCE: "Blocked — insufficient evidence",
};

const MODE_TONE: Record<ReadinessMode, Tone> = {
  MONITORING_ONLY: "ok",
  MANUAL_ACTION_REQUIRED: "warn",
  HUMAN_APPROVAL_REQUIRED: "error",
  BLOCKED_INSUFFICIENT_EVIDENCE: "neutral",
};

/**
 * Readiness mode is derived only from fields the backend already computes for real
 * (decision.human_review_required, decision.priority, and the condition bucket already
 * used fleet-wide) — never fabricated. `AUTOMATIC_ELIGIBLE` is deliberately absent from
 * this derivation: no field in this platform marks a decision as eligible for unattended
 * physical action, and none should until real hardware interlocks/commissioning exist
 * (see the disclaimer below the table).
 */
function readinessModeFor(
  conditionBucket: ReturnType<typeof fleetBucket>,
  decision: DecisionAssessmentResponse | null,
): ReadinessMode {
  if (conditionBucket === "insufficient_evidence" || conditionBucket === "data_quality") {
    return "BLOCKED_INSUFFICIENT_EVIDENCE";
  }
  if (!decision || !decision.human_review_required) return "MONITORING_ONLY";
  if (decision.priority === "URGENT" || decision.priority === "HIGH") {
    return "HUMAN_APPROVAL_REQUIRED";
  }
  return "MANUAL_ACTION_REQUIRED";
}

function flattenMachines(hierarchy: ReturnType<typeof useHierarchy>["data"]) {
  const out: { id: string; name: string; asset_code: string }[] = [];
  if (!hierarchy) return out;
  for (const customer of hierarchy.customers) {
    for (const site of customer.sites) {
      for (const plant of site.plants) {
        for (const line of plant.production_lines) {
          for (const machine of line.machines) {
            out.push({ id: machine.id, name: machine.name, asset_code: machine.asset_code });
          }
        }
      }
    }
  }
  return out;
}

export default function ActionReadinessPage() {
  const hierarchy = useHierarchy();
  const conditions = useFleetLatestConditions();
  const decisions = useFleetLatestDecisions();

  const machines = useMemo(() => flattenMachines(hierarchy.data), [hierarchy.data]);
  const machineById = useMemo(() => new Map(machines.map((m) => [m.id, m])), [machines]);
  const decisionByMachine = useMemo(
    () => new Map((decisions.data ?? []).map((d) => [d.machine_id, d])),
    [decisions.data],
  );

  const rows = useMemo(
    () =>
      (conditions.data ?? [])
        .filter((c) => machineById.has(c.machine_id))
        .map((condition) => {
          const decision = decisionByMachine.get(condition.machine_id) ?? null;
          return {
            condition,
            decision,
            machine: machineById.get(condition.machine_id)!,
            mode: readinessModeFor(fleetBucket(condition), decision),
          };
        })
        .sort((a, b) => a.machine.name.localeCompare(b.machine.name)),
    [conditions.data, decisionByMachine, machineById],
  );

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        title="Lubrication Action Readiness"
        description="Where each monitored asset sits between condition monitoring and a closed-loop maintenance action today — not a control system. No physical machine control is implemented anywhere in this platform."
      />

      <DataState
        isPending={conditions.isPending || hierarchy.isPending}
        isError={conditions.isError}
        error={conditions.error}
        loadingLabel="Loading fleet readiness…"
      >
        {rows.length === 0 ? (
          <EmptyState
            title="No assessed machines yet"
            description="Readiness modes appear once a machine has a persisted condition assessment."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="px-4 py-2 font-medium">Machine</th>
                  <th className="px-4 py-2 font-medium">Condition</th>
                  <th className="px-4 py-2 font-medium">Recommended action</th>
                  <th className="px-4 py-2 font-medium">Urgency</th>
                  <th className="px-4 py-2 font-medium">Readiness mode</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ condition, decision, machine, mode }) => (
                  <tr
                    key={machine.id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/machines/${machine.id}`}
                        className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                      >
                        {machine.name}
                      </Link>
                      <div className="text-xs text-zinc-500 dark:text-zinc-400">
                        {machine.asset_code}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <SeverityBadge value={condition.severity} />
                        <span className="text-xs text-zinc-700 dark:text-zinc-300">
                          {humanize(condition.condition_type)}
                        </span>
                        <ConfidenceBadge value={condition.confidence} />
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">
                      {decision ? humanize(decision.recommended_action) : "Not yet decided"}
                    </td>
                    <td className="px-4 py-2.5">
                      {decision ? <PriorityBadge value={decision.priority} /> : "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <StatusPill tone={MODE_TONE[mode]}>{MODE_LABEL[mode]}</StatusPill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataState>

      <p className="rounded-lg bg-zinc-50/70 p-4 text-xs text-zinc-500 dark:bg-zinc-900/40 dark:text-zinc-400">
        This platform never proposes an <strong>Automatic eligible</strong> mode from live
        data — no field here marks a decision as safe for unattended physical action.
        &ldquo;Automatic eligible&rdquo; would represent policy/readiness simulation only:
        physical actuation requires validated hardware interlocks, commissioning, and
        customer approval, none of which exist in this reference implementation. Every row
        above ends at monitoring, a manual technician action, or an explicit human-approval
        gate.
      </p>
    </div>
  );
}
