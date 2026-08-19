"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { IncidentStateBadge, SeverityBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useIncidents } from "@/hooks/use-incidents";
import { toneForStatus } from "@/lib/terminology";
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
  const incidents = useIncidents();
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

  const openIncidentsByMachine = useMemo(() => {
    const map = new Map<string, { count: number; maxSeverity: string; state: string }>();
    for (const incident of incidents.data ?? []) {
      if (incident.state === "RESOLVED" || incident.state === "CLOSED") continue;
      const existing = map.get(incident.machine_id);
      if (!existing) {
        map.set(incident.machine_id, {
          count: 1,
          maxSeverity: incident.severity,
          state: incident.state,
        });
      } else {
        existing.count += 1;
      }
    }
    return map;
  }, [incidents.data]);

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
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-6 py-10">
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
            title={rows.length === 0 ? "No machines registered yet" : "No machines match this filter"}
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
                  <th className="px-4 py-2 font-medium">Location</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Criticality</th>
                  <th className="px-4 py-2 font-medium">Active incident</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const incidentInfo = openIncidentsByMachine.get(row.machine.id);
                  return (
                    <tr
                      key={row.machine.id}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                    >
                      <td className="px-4 py-2.5">
                        <Link
                          href={`/machines/${row.machine.id}`}
                          className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                        >
                          {row.machine.name}
                        </Link>
                        <div className="text-xs text-zinc-500 dark:text-zinc-400">
                          {row.machine.asset_code}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-zinc-600 dark:text-zinc-400">
                        {row.customerName} / {row.siteName} / {row.plantName} / {row.lineName}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-600 dark:text-zinc-400">
                        {row.machine.machine_type}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusPill tone={toneForStatus(row.machine.status)}>
                          {row.machine.status}
                        </StatusPill>
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusPill tone={toneForStatus(row.machine.criticality)}>
                          {row.machine.criticality}
                        </StatusPill>
                      </td>
                      <td className="px-4 py-2.5">
                        {incidentInfo ? (
                          <div className="flex items-center gap-1.5">
                            <SeverityBadge value={incidentInfo.maxSeverity} />
                            <IncidentStateBadge value={incidentInfo.state} />
                            {incidentInfo.count > 1 && (
                              <span className="text-xs text-zinc-500">+{incidentInfo.count - 1}</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-zinc-400 dark:text-zinc-600">None</span>
                        )}
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
