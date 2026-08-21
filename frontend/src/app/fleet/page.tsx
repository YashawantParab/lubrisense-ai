"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { ConfidenceBadge, IncidentStateBadge, SeverityBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useFleetLatestConditions } from "@/hooks/use-intelligence";
import { usePriorityIncident } from "@/hooks/use-priority-incident";
import { FLEET_BUCKET_TONE, fleetBucket } from "@/lib/fleet-condition";
import { humanize, toneForStatus } from "@/lib/terminology";
import type { HierarchyMachine } from "@/lib/api/asset-hierarchy-types";

interface FleetRow {
  machine: HierarchyMachine;
  customerName: string;
  siteName: string;
  plantName: string;
  lineName: string;
}

type AttentionFilter = "all" | "needs-attention";

export default function FleetPage() {
  usePageTitle("Fleet");
  const hierarchy = useHierarchy();
  const { data: incidents, priorityIncident } = usePriorityIncident();
  const conditions = useFleetLatestConditions();
  const [search, setSearch] = useState("");
  const [attentionFilter, setAttentionFilter] = useState<AttentionFilter>("all");

  const rows: FleetRow[] = useMemo(() => {
    if (!hierarchy.data) return [];
    const out: FleetRow[] = [];
    for (const customer of hierarchy.data.customers) {
      for (const site of customer.sites) {
        for (const plant of site.plants) {
          for (const line of plant.production_lines) {
            for (const machine of line.machines) {
              out.push({
                machine,
                customerName: customer.name,
                siteName: site.name,
                plantName: plant.name,
                lineName: line.name,
              });
            }
          }
        }
      }
    }
    return out;
  }, [hierarchy.data]);

  const conditionByMachine = useMemo(
    () => new Map((conditions.data ?? []).map((c) => [c.machine_id, c])),
    [conditions.data],
  );

  const openIncidentsByMachine = useMemo(() => {
    const map = new Map<
      string,
      { count: number; maxSeverity: string; state: string; conditionType: string }
    >();
    for (const incident of incidents ?? []) {
      if (incident.state === "RESOLVED" || incident.state === "CLOSED") continue;
      const existing = map.get(incident.machine_id);
      if (!existing) {
        map.set(incident.machine_id, {
          count: 1,
          maxSeverity: incident.severity,
          state: incident.state,
          conditionType: incident.incident_type,
        });
      } else {
        existing.count += 1;
      }
    }
    return map;
  }, [incidents]);

  // A machine that just recovered from a real incident is a stronger, more interesting
  // story than an untouched "healthy" machine — collapsing it into a bare "Normal
  // operation" pill the moment it resolves hides that story. Surfaces the single most
  // recent resolved/closed incident per machine so it stays visible after recovery.
  const recentResolvedByMachine = useMemo(() => {
    const map = new Map<string, { incidentId: string; severity: string; resolvedAt: string }>();
    for (const incident of incidents ?? []) {
      if (incident.state !== "RESOLVED" && incident.state !== "CLOSED") continue;
      const at = incident.resolved_at ?? incident.closed_at ?? incident.first_detected_at;
      const existing = map.get(incident.machine_id);
      if (!existing || new Date(at).getTime() > new Date(existing.resolvedAt).getTime()) {
        map.set(incident.machine_id, {
          incidentId: incident.id,
          severity: incident.severity,
          resolvedAt: at,
        });
      }
    }
    return map;
  }, [incidents]);

  const filteredRows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (term) {
        const haystack = `${row.machine.name} ${row.machine.asset_code}`.toLowerCase();
        if (!haystack.includes(term)) return false;
      }
      if (attentionFilter === "needs-attention") {
        return openIncidentsByMachine.has(row.machine.id);
      }
      return true;
    });
  }, [rows, search, attentionFilter, openIncidentsByMachine]);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        title="Fleet"
        description="Every machine across your sites, with operating status and active-incident context in one place."
      />

      <DataState
        isPending={hierarchy.isPending}
        isError={hierarchy.isError}
        error={hierarchy.error}
        loadingLabel="Loading fleet…"
      >
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search machine name or asset code…"
            className="w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            aria-label="Search machines"
          />
          <div className="flex gap-1 rounded-md border border-zinc-300 p-0.5 text-xs dark:border-zinc-700">
            {(["all", "needs-attention"] as AttentionFilter[]).map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setAttentionFilter(filter)}
                className={`rounded px-2.5 py-1 font-medium ${
                  attentionFilter === filter
                    ? "bg-sky-600 text-white"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }`}
              >
                {filter === "all" ? "All machines" : "Needs attention"}
              </button>
            ))}
          </div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {filteredRows.length} of {rows.length} machines
          </span>
        </div>

        {filteredRows.length === 0 ? (
          <EmptyState
            title={
              rows.length === 0 ? "No machines registered yet" : "No machines match this filter"
            }
            description={
              rows.length === 0
                ? "Commission a machine to see it here."
                : "Try clearing the search or switching back to all machines."
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="px-4 py-2 font-medium">Machine</th>
                  <th className="px-4 py-2 font-medium">Condition</th>
                  <th className="px-4 py-2 font-medium">Location</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Criticality</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const incidentInfo = openIncidentsByMachine.get(row.machine.id);
                  const isPriority = priorityIncident?.machine_id === row.machine.id;
                  return (
                    <tr
                      key={row.machine.id}
                      className={`border-b border-zinc-100 last:border-0 dark:border-zinc-800 ${
                        isPriority ? "bg-sky-50/60 dark:bg-sky-500/[0.06]" : ""
                      }`}
                    >
                      <td
                        className={`px-4 py-2.5 ${isPriority ? "border-l-2 border-sky-500" : ""}`}
                      >
                        <div className="flex items-center gap-1.5">
                          <Link
                            href={`/machines/${row.machine.id}`}
                            className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                          >
                            {row.machine.name}
                          </Link>
                          {isPriority && (
                            <span
                              title="The machine with the most complete, real intelligence story right now"
                              className="rounded-full bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-sky-700 uppercase dark:bg-sky-500/15 dark:text-sky-400"
                            >
                              Priority story
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-zinc-500 dark:text-zinc-400">
                          {row.machine.asset_code} · {row.machine.machine_type}
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        {(() => {
                          const condition = conditionByMachine.get(row.machine.id);
                          return (
                            <div className="flex flex-wrap items-center gap-1.5">
                              {condition ? (
                                <>
                                  <StatusPill tone={FLEET_BUCKET_TONE[fleetBucket(condition)]}>
                                    {humanize(condition.condition_type)}
                                  </StatusPill>
                                  <ConfidenceBadge value={condition.confidence} />
                                </>
                              ) : (
                                <StatusPill tone="neutral">Not yet assessed</StatusPill>
                              )}
                            </div>
                          );
                        })()}
                        {incidentInfo ? (
                          <div className="mt-1 flex flex-wrap items-center gap-1.5">
                            <IncidentStateBadge value={incidentInfo.state} />
                            {incidentInfo.count > 1 && (
                              <span className="text-xs text-zinc-500">
                                +{incidentInfo.count - 1}
                              </span>
                            )}
                          </div>
                        ) : (
                          recentResolvedByMachine.has(row.machine.id) && (
                            <Link
                              href={`/incidents/${recentResolvedByMachine.get(row.machine.id)!.incidentId}`}
                              className="mt-1 flex items-center gap-1 text-xs text-zinc-500 hover:underline dark:text-zinc-400"
                            >
                              Recently resolved
                              <SeverityBadge
                                value={recentResolvedByMachine.get(row.machine.id)!.severity}
                              />
                              <RelativeTime
                                iso={recentResolvedByMachine.get(row.machine.id)!.resolvedAt}
                                className="text-zinc-400 dark:text-zinc-600"
                              />
                            </Link>
                          )
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-zinc-600 dark:text-zinc-400">
                        {row.customerName} / {row.siteName} / {row.plantName} / {row.lineName}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusPill tone={toneForStatus(row.machine.status)}>
                          {humanize(row.machine.status)}
                        </StatusPill>
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusPill tone={toneForStatus(row.machine.criticality)}>
                          {humanize(row.machine.criticality)}
                        </StatusPill>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </DataState>
    </div>
  );
}
