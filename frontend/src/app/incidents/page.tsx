"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { IncidentStateBadge, PriorityBadge, SeverityBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useEvaluateMachine, useIncidents } from "@/hooks/use-incidents";
import { useAuth } from "@/lib/auth/context";
import { humanize } from "@/lib/terminology";

export default function IncidentsPage() {
  usePageTitle("Incidents");
  const { can } = useAuth();
  const hierarchy = useHierarchy();
  const [machineId, setMachineId] = useState("");
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

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
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
        {(incidents.data ?? []).length === 0 ? (
          <EmptyState
            title="No incidents"
            description="Incidents are created automatically when evidence warrants attention — none have been detected yet."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="px-4 py-2 font-medium">Title</th>
                  <th className="px-4 py-2 font-medium">Severity</th>
                  <th className="px-4 py-2 font-medium">Priority</th>
                  <th className="px-4 py-2 font-medium">State</th>
                  <th className="px-4 py-2 font-medium">Evidence</th>
                  <th className="px-4 py-2 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {(incidents.data ?? []).map((incident) => (
                  <tr
                    key={incident.id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                  >
                    <td className="px-4 py-2">
                      <Link
                        href={`/incidents/${incident.id}`}
                        className="text-sky-600 hover:underline dark:text-sky-400"
                      >
                        {incident.title}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      <SeverityBadge value={incident.severity} />
                    </td>
                    <td className="px-4 py-2">
                      <PriorityBadge value={incident.priority} />
                    </td>
                    <td className="px-4 py-2">
                      <IncidentStateBadge value={incident.state} />
                    </td>
                    <td className="px-4 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                      {incident.condition_assessment_ids.length} condition ·{" "}
                      {incident.rule_finding_ids.length} rule
                    </td>
                    <td className="px-4 py-2 text-xs text-zinc-700 dark:text-zinc-300">
                      <RelativeTime iso={incident.last_updated_at} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataState>
    </div>
  );
}
