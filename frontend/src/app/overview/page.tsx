"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { AttentionQueue } from "@/components/attention-queue";
import { DataState } from "@/components/data-state";
import { ActionReadinessDistribution } from "@/components/action-readiness-distribution";
import { DataTrustSummary } from "@/components/data-trust-summary";
import { FleetConditionDistribution } from "@/components/fleet-condition-distribution";
import { PriorityAssetCard } from "@/components/priority-asset-card";
import { ProvenanceBadge } from "@/components/badges";
import { RecentOutcomes } from "@/components/recent-outcomes";
import { SectionCard } from "@/components/section-card";
import { usePageTitle } from "@/hooks/use-page-title";
import { useIncidents } from "@/hooks/use-incidents";
import { useFleetLatestConditions } from "@/hooks/use-intelligence";
import { useFleetOverview } from "@/hooks/use-overview";
import { useNorthStar } from "@/hooks/use-product-metrics";
import { fleetBucket } from "@/lib/fleet-condition";

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export default function OverviewPage() {
  usePageTitle("Overview");
  const fleet = useFleetOverview();
  const conditions = useFleetLatestConditions();
  const { data: incidents } = useIncidents();
  const northStar = useNorthStar();

  // The single most notable closed-loop story — real, persisted, most-recently-resolved
  // incident with a maintenance outcome, never a guessed/hardcoded machine.
  const mostRecentResolved = useMemo(
    () =>
      (incidents ?? [])
        .filter((i) => i.state === "RESOLVED" || i.state === "CLOSED")
        .sort(
          (a, b) =>
            new Date(b.resolved_at ?? b.closed_at ?? b.last_updated_at).getTime() -
            new Date(a.resolved_at ?? a.closed_at ?? a.last_updated_at).getTime(),
        )[0] ?? null,
    [incidents],
  );

  const statusCounts = useMemo(() => {
    const tally = { monitored: 0, attention: 0, healthy: 0, dataQuality: 0 };
    for (const condition of conditions.data ?? []) {
      tally.monitored += 1;
      const bucket = fleetBucket(condition);
      if (bucket === "attention") tally.attention += 1;
      else if (bucket === "healthy") tally.healthy += 1;
      else if (bucket === "data_quality" || bucket === "insufficient_evidence") {
        tally.dataQuality += 1;
      }
    }
    return tally;
  }, [conditions.data]);

  // Snapshot "now" once per mount rather than calling `Date.now()` inline during render
  // (react-hooks/purity) — a page reviewer keeping this tab open for a while may see a
  // slightly stale 30-day cutoff, which is an acceptable tradeoff for a status count.
  const [nowMs] = useState(() => Date.now());
  const recentlyResolvedCount = useMemo(
    () =>
      (incidents ?? []).filter((i) => {
        if (i.state !== "RESOLVED" && i.state !== "CLOSED") return false;
        const at = i.resolved_at ?? i.closed_at;
        if (!at) return false;
        return nowMs - new Date(at).getTime() < 30 * 24 * 60 * 60 * 1000;
      }).length,
    [incidents, nowMs],
  );

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-10 px-6 py-10 lg:px-10">
      <header>
        <p className="text-xs font-semibold tracking-wide text-sky-600 uppercase dark:text-sky-400">
          Condition-driven lubrication intelligence
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          Fleet overview
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400">
          See which assets need attention, why their lubrication condition is changing, and what
          maintenance should do next — every claim below traces back to persisted platform data.
        </p>
      </header>

      <DataState
        isPending={conditions.isPending}
        isError={conditions.isError}
        error={conditions.error}
      >
        {/* Compact fleet-status stat line — real, seeded counts, never hardcoded. */}
        <div className="flex flex-wrap items-baseline gap-x-10 gap-y-3 border-y border-zinc-100 py-4 dark:border-zinc-800/70">
          {[
            ["Monitored assets", statusCounts.monitored],
            ["Need attention", statusCounts.attention],
            ["Healthy / stable", statusCounts.healthy],
            ["Data-quality constrained", statusCounts.dataQuality],
            ["Recently resolved (30d)", recentlyResolvedCount],
          ].map(([label, value]) => (
            <div key={label as string} className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
                {value}
              </span>
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
            </div>
          ))}
        </div>
      </DataState>

      <AttentionQueue />

      <div className="grid gap-6 lg:grid-cols-2">
        <FleetConditionDistribution />
        <ActionReadinessDistribution />
      </div>

      <DataTrustSummary />

      {mostRecentResolved && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[13px] font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
            Recently resolved
          </h2>
          <PriorityAssetCard incident={mostRecentResolved} />
        </section>
      )}

      <RecentOutcomes />

      <DataState isPending={fleet.isPending} isError={fleet.isError} error={fleet.error}>
        {fleet.data && (
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
        )}
      </DataState>
    </div>
  );
}
