"use client";

import { use } from "react";
import Link from "next/link";

import { ProvenanceBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { KpiStrip } from "@/components/kpi-strip";
import { ActionReadinessPanel } from "@/components/portfolio/action-readiness-panel";
import { CarbonPanel } from "@/components/portfolio/carbon-panel";
import { ConditionBreakdown } from "@/components/portfolio/condition-breakdown";
import { DataTrustPanel } from "@/components/portfolio/data-trust-panel";
import { EnergyEfficiencyPanel } from "@/components/portfolio/energy-efficiency-panel";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { usePageTitle } from "@/hooks/use-page-title";
import { useAreaPerformance } from "@/hooks/use-performance";

export default function AreaDetailPage({ params }: { params: Promise<{ areaKey: string }> }) {
  const { areaKey: rawAreaKey } = use(params);
  // Real area names can contain "/" (e.g. "Metals / Rolling"), so the link that got us
  // here percent-encoded it (%2F). Next.js leaves a single dynamic segment containing an
  // encoded slash undecoded — decode once here so every hook/fetch below works with the
  // plain name, matching `AreaPerformanceTable`'s own `encodeURIComponent` convention.
  const areaKey = decodeURIComponent(rawAreaKey);
  const area = useAreaPerformance(areaKey);

  usePageTitle(area.data?.area ?? "Area");

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-10 px-6 py-10 lg:px-10">
      <DataState
        isPending={area.isPending}
        isError={area.isError}
        error={area.error}
        loadingLabel="Loading area performance…"
      >
        {area.data && (
          <>
            <PageHeader
              breadcrumbs={[
                { label: "Organization", href: "/performance/organization" },
                { label: "Areas" },
              ]}
              title={area.data.area}
              description={
                area.data.site_codes.length > 1
                  ? `Organization-wide rollup for this area — active at ${area.data.site_codes.join(", ")}. Figures below span all of these sites, not one alone.`
                  : `${area.data.site_codes[0] ?? "Unassigned site"} · ${area.data.asset_count} monitored asset${area.data.asset_count === 1 ? "" : "s"}`
              }
              actions={
                <>
                  <ProvenanceBadge value={area.data.provenance} />
                  <span className="text-xs text-zinc-400 dark:text-zinc-600">
                    as of <RelativeTime iso={area.data.as_of} />
                  </span>
                  <Link
                    href={`/fleet?area=${encodeURIComponent(area.data.area)}`}
                    className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  >
                    View this area&rsquo;s fleet →
                  </Link>
                </>
              }
            />

            <KpiStrip
              items={[
                { label: "Monitored assets", value: area.data.asset_count },
                { label: "Need attention", value: area.data.attention_count },
                {
                  label: "Critical attention",
                  value: area.data.critical_attention_count,
                  valueClassName:
                    area.data.critical_attention_count > 0
                      ? "text-red-600 dark:text-red-400"
                      : undefined,
                },
                {
                  label: "Energy opportunities",
                  value: area.data.active_energy_opportunities,
                },
                {
                  label: "Qualified recoveries",
                  value: area.data.qualified_recovery_count,
                  valueClassName:
                    area.data.qualified_recovery_count > 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : undefined,
                },
              ]}
            />

            <ConditionBreakdown distribution={area.data.condition_distribution} />

            <EnergyEfficiencyPanel
              activeOpportunities={area.data.active_energy_opportunities}
              qualifiedRecoveryCount={area.data.qualified_recovery_count}
              qualifiedAvoidedEnergyKwhTotal={area.data.qualified_avoided_energy_kwh_total}
            />

            <CarbonPanel estimatedCo2eKgTotal={area.data.estimated_co2e_kg_total} />

            <div className="grid gap-6 lg:grid-cols-2">
              <ActionReadinessPanel distribution={area.data.action_readiness_distribution} />
              <DataTrustPanel distribution={area.data.data_trust_distribution} />
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}
