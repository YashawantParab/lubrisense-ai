"use client";

import Link from "next/link";
import { useMemo } from "react";

import { ConfidenceBadge, PriorityBadge, SeverityBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useFleetLatestConditions, useFleetLatestDecisions } from "@/hooks/use-intelligence";
import {
  READINESS_MODE_DESCRIPTION,
  READINESS_MODE_LABEL,
  READINESS_MODE_TONE,
  effectiveRecommendedAction,
  readinessEvidenceFor,
  readinessModeFor,
  type ReadinessMode,
} from "@/lib/action-readiness";
import { recommendedActionDisplay } from "@/lib/action-wording";
import { componentFromName } from "@/lib/equipment";
import { humanize } from "@/lib/terminology";

const MODE_ORDER: ReadinessMode[] = [
  "MONITORING_ONLY",
  "MANUAL_ACTION_REQUIRED",
  "HUMAN_APPROVAL_REQUIRED",
  "AUTO_ELIGIBLE_SIMULATION",
  "BLOCKED_INSUFFICIENT_EVIDENCE",
  "BLOCKED_SAFETY_INTERLOCK",
];

function flattenMachines(hierarchy: ReturnType<typeof useHierarchy>["data"]) {
  const out: { id: string; name: string; asset_code: string; status: string }[] = [];
  if (!hierarchy) return out;
  for (const customer of hierarchy.customers) {
    for (const site of customer.sites) {
      for (const plant of site.plants) {
        for (const line of plant.production_lines) {
          for (const machine of line.machines) {
            out.push({
              id: machine.id,
              name: machine.name,
              asset_code: machine.asset_code,
              status: machine.status,
            });
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
          const machine = machineById.get(condition.machine_id)!;
          const decision = decisionByMachine.get(condition.machine_id) ?? null;
          const mode = readinessModeFor(condition, decision, machine.status);
          return {
            condition,
            decision,
            effective: effectiveRecommendedAction(condition, decision),
            machine,
            mode,
            evidence: readinessEvidenceFor(condition, decision, machine.status, mode),
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
          <ul className="flex flex-col divide-y divide-zinc-100 rounded-lg border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
            {rows.map(({ condition, effective, evidence, machine, mode }) => (
              <li key={machine.id} className="flex flex-col gap-2 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <Link
                      href={`/machines/${machine.id}`}
                      className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                    >
                      {machine.name}
                    </Link>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">{machine.asset_code}</p>
                  </div>
                  <StatusPill tone={READINESS_MODE_TONE[mode]} size="lg">
                    {READINESS_MODE_LABEL[mode]}
                  </StatusPill>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  <SeverityBadge value={condition.severity} />
                  <span className="text-xs text-zinc-700 dark:text-zinc-300">
                    {humanize(condition.condition_type)}
                  </span>
                  <ConfidenceBadge value={condition.confidence} />
                </div>

                <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
                  <span>
                    <span className="text-xs text-zinc-400 dark:text-zinc-600">Recommended: </span>
                    <span className="font-medium text-zinc-800 dark:text-zinc-200">
                      {effective
                        ? recommendedActionDisplay(
                            effective.action,
                            componentFromName(machine.name),
                          )
                        : "Not yet decided"}
                    </span>
                  </span>
                  {effective && <PriorityBadge value={effective.priority} />}
                </div>

                <details className="text-xs text-zinc-600 dark:text-zinc-400">
                  <summary className="cursor-pointer font-medium text-sky-600 select-none dark:text-sky-400">
                    Why this mode
                  </summary>
                  <dl className="mt-1.5 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
                    {evidence.map((item) => (
                      <div key={item.label} className="contents">
                        <dt className="text-zinc-400 dark:text-zinc-600">{item.label}:</dt>
                        <dd className="text-zinc-700 dark:text-zinc-300">{item.value}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              </li>
            ))}
          </ul>
        )}
      </DataState>

      <SectionCard title="Readiness modes">
        <dl className="grid gap-3 sm:grid-cols-2">
          {MODE_ORDER.map((mode) => (
            <div key={mode} className="flex flex-col gap-1">
              <dt>
                <StatusPill tone={READINESS_MODE_TONE[mode]}>
                  {READINESS_MODE_LABEL[mode]}
                </StatusPill>
              </dt>
              <dd className="text-xs text-zinc-600 dark:text-zinc-400">
                {READINESS_MODE_DESCRIPTION[mode]}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <strong>Auto-eligible</strong> and <strong>safety/interlock</strong> are real, live
          classifications, not placeholders — but no machine in this fleet currently occupies
          either. Every recommended action here is a human physical-presence inspection or
          verification step (never a control command), so nothing is structurally eligible for
          automation yet; every asset is in a normal <code>Monitored</code> state, so no interlock
          is active.
        </p>
      </SectionCard>

      <SectionCard title="What this platform controls today">
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <h3 className="text-xs font-semibold tracking-wide text-emerald-700 uppercase dark:text-emerald-400">
              Implemented
            </h3>
            <ul className="mt-2 space-y-1.5 text-sm text-zinc-700 dark:text-zinc-300">
              <li>Condition monitoring from real telemetry, rules, state estimation, and ML</li>
              <li>Decision support — a recommended action, priority, and rationale</li>
              <li>Human-approved action workflow — incident and maintenance case tracking</li>
              <li>Action-readiness simulation — which mode an action would fall into</li>
            </ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
              Not implemented
            </h3>
            <ul className="mt-2 space-y-1.5 text-sm text-zinc-700 dark:text-zinc-300">
              <li>Physical autonomous lubrication control</li>
            </ul>
            <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
              A real closed-loop control deployment would additionally require validated actuator
              interfaces, interlocks, actuation feedback confirmation, machine commissioning,
              safe-state logic, cybersecurity review, and customer authorization — none of which
              exist in this reference implementation.
            </p>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
