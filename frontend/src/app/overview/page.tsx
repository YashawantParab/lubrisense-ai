"use client";

import Link from "next/link";
import { useMemo } from "react";

import { IncidentStateBadge, ProvenanceBadge, SeverityBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PriorityAssetCard } from "@/components/priority-asset-card";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useFleetOverview } from "@/hooks/use-overview";
import { usePriorityIncident } from "@/hooks/use-priority-incident";
import { useNorthStar } from "@/hooks/use-product-metrics";
import { customerStatusTone, humanize } from "@/lib/terminology";

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export default function OverviewPage() {
  usePageTitle("Overview");
  const fleet = useFleetOverview();
  const { data: incidents, priorityIncident } = usePriorityIncident();
  const northStar = useNorthStar();

  const otherAttentionIncidents = useMemo(
    () =>
      (incidents ?? [])
        .filter((i) => i.id !== priorityIncident?.id)
        .filter((i) => i.state !== "RESOLVED" && i.state !== "CLOSED")
        .sort(
          (a, b) =>
            new Date(b.first_detected_at).getTime() - new Date(a.first_detected_at).getTime(),
        )
        .slice(0, 6),
    [incidents, priorityIncident],
  );

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-8 px-6 py-10 lg:px-10">
      <PageHeader
        title="Overview"
        description="What's happening across your fleet, what the system believes it means, and what to do about it — every claim below traces back to persisted platform data."
      />

      {priorityIncident && <PriorityAssetCard incident={priorityIncident} />}

      <DataState isPending={fleet.isPending} isError={fleet.isError} error={fleet.error}>
        {fleet.data && (
          <div className="flex flex-col gap-8">
            {/* Compact fleet context — an open stats line, not a grid of KPI tiles. */}
            <div className="flex flex-wrap items-baseline gap-x-10 gap-y-3 border-y border-zinc-100 py-4 dark:border-zinc-800/70">
              {[
                ["Customer accounts", fleet.data.total_customer_accounts],
                ["Sites", fleet.data.total_sites],
                ["Machines", fleet.data.total_machines],
                ["Open incidents", fleet.data.service_burden.open_incidents],
              ].map(([label, value]) => (
                <div key={label as string} className="flex items-baseline gap-2">
                  <span className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
                    {value}
                  </span>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
                </div>
              ))}
            </div>

            {otherAttentionIncidents.length > 0 && (
              <SectionCard
                title="Also needs attention"
                actions={
                  <Link
                    href="/fleet"
                    className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                  >
                    View fleet
                  </Link>
                }
              >
                <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {otherAttentionIncidents.map((incident) => (
                    <li key={incident.id} className="flex items-center justify-between gap-3 py-2">
                      <div className="flex items-center gap-2">
                        <SeverityBadge value={incident.severity} />
                        <Link
                          href={`/incidents/${incident.id}`}
                          className="text-sm text-sky-700 hover:underline dark:text-sky-400"
                        >
                          {incident.title}
                        </Link>
                      </div>
                      <div className="flex items-center gap-2">
                        <IncidentStateBadge value={incident.state} />
                        <RelativeTime
                          iso={incident.first_detected_at}
                          className="text-xs text-zinc-400 dark:text-zinc-600"
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              </SectionCard>
            )}

            {!priorityIncident && otherAttentionIncidents.length === 0 && (
              <EmptyState
                title="Nothing needs attention right now"
                description="No incidents recorded across your fleet yet."
              />
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <SectionCard title="Asset coverage">
                <dl className="grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <dt className="text-zinc-500 dark:text-zinc-400">Instrumented</dt>
                    <dd className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
                      {pct(fleet.data.asset_coverage.instrumentation_coverage_ratio)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-zinc-500 dark:text-zinc-400">Telemetry fresh</dt>
                    <dd className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
                      {pct(fleet.data.asset_coverage.telemetry_freshness_ratio)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-zinc-500 dark:text-zinc-400">Condition coverage</dt>
                    <dd className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
                      {pct(fleet.data.asset_coverage.condition_coverage_ratio)}
                    </dd>
                  </div>
                </dl>
              </SectionCard>

              <SectionCard
                title="North Star"
                actions={
                  <Link
                    href="/metrics"
                    className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                  >
                    View all metrics
                  </Link>
                }
              >
                {northStar.data ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
                        {northStar.data.value === null
                          ? "Not enough data yet"
                          : `${Math.round(northStar.data.value * 100)}%`}
                      </p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">
                        Meaningful issues detected with actionable lead time
                      </p>
                    </div>
                    <ProvenanceBadge value={northStar.data.provenance} />
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
                )}
              </SectionCard>
            </div>

            <SectionCard title="Customers by status">
              <div className="flex flex-wrap gap-2">
                {Object.entries(fleet.data.customers_by_status).map(([status, count]) => (
                  <StatusPill key={status} tone={customerStatusTone(status)}>
                    {humanize(status)}: {count}
                  </StatusPill>
                ))}
                {Object.keys(fleet.data.customers_by_status).length === 0 && (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    No customer accounts registered yet.
                  </p>
                )}
              </div>
            </SectionCard>
          </div>
        )}
      </DataState>
    </div>
  );
}
