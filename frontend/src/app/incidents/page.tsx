"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { IncidentStateBadge, PriorityBadge, SeverityBadge } from "@/components/badges";
import { evidenceBackingLine } from "@/components/condition-evidence";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useEvaluateMachine, useIncidents } from "@/hooks/use-incidents";
import { useMaintenanceCases } from "@/hooks/use-maintenance";
import { useAuth } from "@/lib/auth/context";
import { humanize } from "@/lib/terminology";

const STATE_FILTERS = ["ALL", "OPEN", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"] as const;
type StateFilter = (typeof STATE_FILTERS)[number];

const STATE_FILTER_LABEL: Record<StateFilter, string> = {
  ALL: "All",
  OPEN: "Open",
  ACKNOWLEDGED: "Acknowledged",
  INVESTIGATING: "Investigating",
  RESOLVED: "Resolved",
};

// Real IncidentState values (backend/app/domain/enums.py) grouped under each filter chip
// — "Open" covers every not-yet-acknowledged state, "Resolved" covers both terminal states.
const STATE_FILTER_MATCH: Record<StateFilter, (state: string) => boolean> = {
  ALL: () => true,
  OPEN: (s) => s === "DETECTED" || s === "OPEN" || s === "REOPENED",
  ACKNOWLEDGED: (s) => s === "ACKNOWLEDGED",
  INVESTIGATING: (s) => s === "INVESTIGATING" || s === "ACTION_PLANNED",
  RESOLVED: (s) => s === "RESOLVED" || s === "CLOSED",
};

export default function IncidentsPage() {
  usePageTitle("Incidents");
  const { can } = useAuth();
  const hierarchy = useHierarchy();
  const [machineId, setMachineId] = useState("");
  const [stateFilter, setStateFilter] = useState<StateFilter>("ALL");
  const incidents = useIncidents();

  const machines = useMemo(
    () =>
      hierarchy.data?.customers.flatMap((customer) =>
        customer.sites.flatMap((site) =>
          site.plants.flatMap((plant) => plant.production_lines.flatMap((line) => line.machines)),
        ),
      ) ?? [],
    [hierarchy.data],
  );
  const effectiveMachineId = machineId || machines[0]?.id || "";
  const evaluate = useEvaluateMachine(effectiveMachineId);
  const canEvaluate = can("INCIDENT_MANAGE");
  const cases = useMaintenanceCases();

  const machineName = useMemo(() => new Map(machines.map((m) => [m.id, m.name])), [machines]);
  const caseByIncident = useMemo(
    () => new Map((cases.data ?? []).map((c) => [c.incident_id, c])),
    [cases.data],
  );

  const filteredIncidents = useMemo(
    () =>
      (incidents.data ?? []).filter((incident) => STATE_FILTER_MATCH[stateFilter](incident.state)),
    [incidents.data, stateFilter],
  );

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        title="Incidents"
        description="Correlated evidence for one evolving operational problem — never one row per evaluation cycle."
      />

      {canEvaluate && (
        <details className="rounded-lg border border-dashed border-zinc-300 px-4 py-2 dark:border-zinc-700">
          <summary className="cursor-pointer text-xs font-medium text-zinc-500 select-none dark:text-zinc-400">
            Engineering: manually re-evaluate a machine
          </summary>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select
              value={effectiveMachineId}
              onChange={(event) => setMachineId(event.target.value)}
              className="min-w-52 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            >
              {machines.map((machine) => (
                <option key={machine.id} value={machine.id}>
                  {machine.name} · {machine.asset_code}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!effectiveMachineId || evaluate.isPending}
              onClick={() => evaluate.mutate()}
              className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              {evaluate.isPending ? "Evaluating…" : "Evaluate now"}
            </button>
          </div>
          {evaluate.isSuccess && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              {evaluate.data
                ? `Incident ${evaluate.data.state === "OPEN" ? "created/updated" : "updated"}: ${humanize(evaluate.data.incident_type)}.`
                : "Current evidence does not warrant an incident (healthy, ambiguous, insufficient, or data-quality limited)."}
            </p>
          )}
        </details>
      )}

      <DataState
        isPending={incidents.isPending}
        isError={incidents.isError}
        error={incidents.error}
        loadingLabel="Loading incidents…"
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 rounded-md border border-zinc-300 p-0.5 text-xs dark:border-zinc-700">
            {STATE_FILTERS.map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setStateFilter(filter)}
                className={`rounded px-2.5 py-1 font-medium ${
                  stateFilter === filter
                    ? "bg-sky-600 text-white"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }`}
              >
                {STATE_FILTER_LABEL[filter]}
              </button>
            ))}
          </div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {filteredIncidents.length} of {(incidents.data ?? []).length} incidents
          </span>
        </div>

        {filteredIncidents.length === 0 ? (
          <EmptyState
            title={
              (incidents.data ?? []).length === 0
                ? "No incidents"
                : "No incidents match this filter"
            }
            description={
              (incidents.data ?? []).length === 0
                ? "Incidents are created automatically when evidence warrants attention — none have been detected yet."
                : "Try a different filter."
            }
          />
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {filteredIncidents.map((incident) => {
              const linkedCase = caseByIncident.get(incident.id);
              return (
                <li key={incident.id} className="flex flex-wrap items-start gap-x-8 gap-y-2 py-4">
                  <div className="min-w-56 flex-1">
                    <Link
                      href={`/incidents/${incident.id}`}
                      className="text-base font-medium text-sky-700 hover:underline dark:text-sky-400"
                    >
                      {incident.title}
                    </Link>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {machineName.get(incident.machine_id) ?? "Unknown machine"} ·{" "}
                      {evidenceBackingLine(incident)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <SeverityBadge value={incident.severity} />
                    <PriorityBadge value={incident.priority} />
                    <IncidentStateBadge value={incident.state} />
                  </div>
                  <div className="min-w-40 text-sm text-zinc-600 dark:text-zinc-400">
                    {linkedCase
                      ? humanize(linkedCase.recommended_action)
                      : "No action recommended yet"}
                  </div>
                  <div className="ml-auto text-xs text-zinc-400 dark:text-zinc-600">
                    <RelativeTime iso={incident.last_updated_at} />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </DataState>
    </div>
  );
}
