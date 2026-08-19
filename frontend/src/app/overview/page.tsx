"use client";

import Link from "next/link";

import { IncidentStateBadge, ProvenanceBadge, SeverityBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useFleetOverview } from "@/hooks/use-overview";
import { useIncidents } from "@/hooks/use-incidents";
import { useNorthStar } from "@/hooks/use-product-metrics";
import { customerStatusTone, humanize } from "@/lib/terminology";

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export default function OverviewPage() {
  usePageTitle("Overview");
  const fleet = useFleetOverview();
  const incidents = useIncidents();
  const northStar = useNorthStar();

  const attentionIncidents = (incidents.data ?? [])
    .filter((i) => i.state !== "RESOLVED" && i.state !== "CLOSED")
    .sort((a, b) => new Date(b.first_detected_at).getTime() - new Date(a.first_detected_at).getTime())
    .slice(0, 8);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Overview"
        description="Your operational home screen — real fleet coverage, active incidents, and North-Star progress, all traceable to persisted platform data."
      />

      <DataState isPending={fleet.isPending} isError={fleet.isError} error={fleet.error}>
        {fleet.data && (
          <div className="flex flex-col gap-6">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              {[
                ["Customer accounts", fleet.data.total_customer_accounts],
                ["Sites", fleet.data.total_sites],
                ["Machines", fleet.data.total_machines],
                ["Open incidents", fleet.data.service_burden.open_incidents],
              ].map(([label, value]) => (
                <div
                  key={label as string}
                  className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <div className="text-xs text-zinc-500 dark:text-zinc-400">{label}</div>
                  <div className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
                    {value}
                  </div>
                </div>
              ))}
            </div>

            <SectionCard
              title="Needs attention"
              actions={
                <Link href="/fleet" className="text-xs text-sky-600 hover:underline dark:text-sky-400">
                  View fleet
                </Link>
              }
            >
              {attentionIncidents.length === 0 ? (
                <EmptyState
                  title="Nothing needs attention right now"
                  description="No open incidents across your fleet."
                />
              ) : (
                <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {attentionIncidents.map((incident) => (
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
              )}
            </SectionCard>

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
                  <Link href="/metrics" className="text-xs text-sky-600 hover:underline dark:text-sky-400">
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
