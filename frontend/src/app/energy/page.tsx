"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import {
  AttributionLevelBadge,
  CarbonEstimateStatusBadge,
  EnergyBucketBadge,
  EnergyOutcomeStatusBadge,
} from "@/components/badges";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { usePageTitle } from "@/hooks/use-page-title";
import { useEnergyQueue, useOrganizationPerformance } from "@/hooks/use-performance";
import { formatKw, formatPct } from "@/lib/energy-format";
import type { EnergyAsset } from "@/lib/api/performance-types";

type EnergyFilter =
  "all" | "opportunity" | "awaiting-verification" | "qualified" | "normal" | "insufficient";

const FILTER_LABEL: Record<EnergyFilter, string> = {
  all: "All",
  opportunity: "Opportunity",
  "awaiting-verification": "Awaiting verification",
  qualified: "Qualified outcome",
  normal: "Normal",
  insufficient: "Insufficient data",
};

// Presentation-only grouping of the backend's own EnergyPortfolioBucket enum
// (Enterprise Product Rebuild §7) — never a re-derivation of the bucket itself. Every
// bucket the backend can return maps to exactly one filter here so a row is never
// silently excluded from every category.
const FILTER_MATCH: Record<EnergyFilter, (bucket: string) => boolean> = {
  all: () => true,
  opportunity: (b) => b === "ATTRIBUTION_SUPPORTED_OPPORTUNITY" || b === "ACTIVE_ELEVATED_ENERGY",
  "awaiting-verification": (b) =>
    b === "OUTCOME_AWAITING_VERIFICATION" ||
    b === "INCONCLUSIVE_OUTCOME" ||
    b === "OUTCOME_DETERIORATED",
  qualified: (b) => b === "QUALIFIED_ENERGY_RECOVERY",
  normal: (b) => b === "NORMAL_ENERGY_BEHAVIOR",
  insufficient: (b) => b === "INSUFFICIENT_ENERGY_DATA",
};

export default function EnergyWorkspacePage() {
  return (
    <Suspense fallback={null}>
      <EnergyWorkspacePageContent />
    </Suspense>
  );
}

function EnergyWorkspacePageContent() {
  usePageTitle("Energy & Efficiency");
  const org = useOrganizationPerformance();
  const energy = useEnergyQueue(200);
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filter = (searchParams.get("status") as EnergyFilter | null) ?? "all";
  const setFilter = (value: EnergyFilter) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === "all") params.delete("status");
    else params.set("status", value);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const rows = useMemo(() => energy.data ?? [], [energy.data]);
  const filtered = useMemo(
    () => rows.filter((r) => FILTER_MATCH[filter](r.energy_bucket)),
    [rows, filter],
  );

  const monitoredAssets = org.data?.portfolio.monitored_assets;
  const assessableAssets = org.data?.energy_efficiency.energy_assessable_assets;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        breadcrumbs={[{ label: "Organization", href: "/performance/organization" }]}
        title="Energy & efficiency"
        description="Every machine with a commissioned power sensor and a computed energy assessment — actual power against its contextual expectation, lubrication-attribution evidence where present, and any qualified outcome from a completed intervention."
      />

      {monitoredAssets !== undefined && assessableAssets !== undefined && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            {assessableAssets} of {monitoredAssets} monitored assets
          </span>{" "}
          are currently energy-assessable — the rest have no commissioned power sensor, so no energy
          comparison can be made for them. This is a coverage gap, not a &quot;normal&quot; reading.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1 rounded-md border border-zinc-300 p-0.5 text-xs dark:border-zinc-700">
          {(Object.keys(FILTER_LABEL) as EnergyFilter[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`rounded px-2.5 py-1 font-medium ${
                filter === key
                  ? "bg-sky-600 text-white"
                  : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
              }`}
            >
              {FILTER_LABEL[key]}
            </button>
          ))}
        </div>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {filtered.length} of {rows.length} energy-assessable assets
        </span>
      </div>

      <DataState
        isPending={energy.isPending}
        isError={energy.isError}
        error={energy.error}
        loadingLabel="Loading energy assessments…"
      >
        {filtered.length === 0 ? (
          <EmptyState
            title={
              rows.length === 0 ? "No energy-assessable assets yet" : "No assets match this filter"
            }
            description={
              rows.length === 0
                ? "No machine has a commissioned power sensor with a computed energy assessment yet."
                : "Try clearing the filter or switching back to all assets."
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="px-4 py-2 font-medium">Asset</th>
                  <th className="px-4 py-2 font-medium">Site</th>
                  <th className="px-4 py-2 font-medium">Actual power</th>
                  <th className="px-4 py-2 font-medium">Expected power</th>
                  <th className="px-4 py-2 font-medium">Residual</th>
                  <th className="px-4 py-2 font-medium">Energy status</th>
                  <th className="px-4 py-2 font-medium">Attribution</th>
                  <th className="px-4 py-2 font-medium">Outcome</th>
                  <th className="px-4 py-2 font-medium">Avoided energy</th>
                  <th className="px-4 py-2 font-medium">CO2e</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row: EnergyAsset) => (
                  <tr
                    key={row.ref.machine_id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                  >
                    <td className="px-4 py-2">
                      <Link
                        href={`/machines/${row.ref.machine_id}`}
                        className="font-medium text-sky-600 hover:underline dark:text-sky-400"
                      >
                        {row.ref.name}
                      </Link>
                      <div className="text-xs text-zinc-400 dark:text-zinc-600">
                        {row.ref.asset_code}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                      {row.ref.site_name}
                    </td>
                    <td className="px-4 py-2 tabular-nums">{formatKw(row.actual_power_kw)}</td>
                    <td className="px-4 py-2 tabular-nums">{formatKw(row.expected_power_kw)}</td>
                    <td className="px-4 py-2 tabular-nums">{formatPct(row.residual_pct)}</td>
                    <td className="px-4 py-2">
                      <EnergyBucketBadge value={row.energy_bucket} />
                    </td>
                    <td className="px-4 py-2">
                      {row.attribution_level ? (
                        <AttributionLevelBadge value={row.attribution_level} />
                      ) : (
                        <span className="text-xs text-zinc-400 dark:text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {row.latest_outcome_status ? (
                        <EnergyOutcomeStatusBadge value={row.latest_outcome_status} />
                      ) : (
                        <span className="text-xs text-zinc-400 dark:text-zinc-600">
                          No intervention yet
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 tabular-nums">
                      {row.latest_outcome_avoided_kwh !== null
                        ? `~${row.latest_outcome_avoided_kwh.toFixed(1)} kWh`
                        : "—"}
                    </td>
                    <td className="px-4 py-2">
                      {row.carbon_status ? (
                        <div className="flex flex-col gap-0.5">
                          <CarbonEstimateStatusBadge value={row.carbon_status} />
                          {row.carbon_estimated_kg !== null && (
                            <span className="text-xs text-zinc-500 dark:text-zinc-400">
                              ~{row.carbon_estimated_kg.toFixed(2)} kg CO2e
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-zinc-400 dark:text-zinc-600">
                          Not eligible
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataState>

      <p className="text-xs text-zinc-400 dark:text-zinc-600">
        &quot;Opportunity&quot; is elevated contextual energy demand — never yet a savings claim.
        &quot;Qualified outcome&quot; requires a completed maintenance intervention with a
        comparable pre/post measurement window.{" "}
        <Link href="/data-quality" className="text-sky-600 hover:underline dark:text-sky-400">
          See Data Quality →
        </Link>
      </p>
    </div>
  );
}
