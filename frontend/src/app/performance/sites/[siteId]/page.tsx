"use client";

import { Suspense, use } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { DataState } from "@/components/data-state";
import { ProvenanceBadge } from "@/components/badges";
import { ActionReadinessPanel } from "@/components/portfolio/action-readiness-panel";
import { AreaPerformanceTable } from "@/components/portfolio/area-performance-table";
import { CarbonPanel } from "@/components/portfolio/carbon-panel";
import { ConditionBreakdown } from "@/components/portfolio/condition-breakdown";
import { DataTrustPanel } from "@/components/portfolio/data-trust-panel";
import { EnergyEfficiencyPanel } from "@/components/portfolio/energy-efficiency-panel";
import { MaintenanceOutcomesPanel } from "@/components/portfolio/maintenance-outcomes-panel";
import { PortfolioAttentionQueue } from "@/components/portfolio/portfolio-attention-queue";
import { PortfolioRecentOutcomes } from "@/components/portfolio/portfolio-recent-outcomes";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import { WorkspaceTabs } from "@/components/workspace-tabs";
import { usePageTitle } from "@/hooks/use-page-title";
import { useAreaPerformances, useSitePerformance } from "@/hooks/use-performance";

type SiteView = "overview" | "reliability" | "maintenance" | "energy" | "data-trust" | "outcomes";

const SITE_TABS: { key: SiteView; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "reliability", label: "Reliability" },
  { key: "maintenance", label: "Maintenance" },
  { key: "energy", label: "Energy & Efficiency" },
  { key: "data-trust", label: "Data Trust" },
  { key: "outcomes", label: "Outcomes" },
];

export default function SiteDetailPage({ params }: { params: Promise<{ siteId: string }> }) {
  return (
    <Suspense fallback={null}>
      <SiteDetailPageContent params={params} />
    </Suspense>
  );
}

function SiteDetailPageContent({ params }: { params: Promise<{ siteId: string }> }) {
  const { siteId } = use(params);
  const site = useSitePerformance(siteId);
  const areas = useAreaPerformances();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  usePageTitle(site.data?.site_name ?? "Site");

  const view = (searchParams.get("view") as SiteView | null) ?? "overview";
  const setView = (value: SiteView) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === "overview") params.delete("view");
    else params.set("view", value);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const siteAreas = (areas.data ?? []).filter((area) =>
    area.site_codes.includes(site.data?.site_code ?? "__none__"),
  );

  const dataTrustLimited = site.data
    ? (site.data.data_trust_distribution["ASSESSMENT_BLOCKED"] ?? 0) +
      (site.data.data_trust_distribution["ACTION_BLOCKED"] ?? 0)
    : 0;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-8 px-6 py-10 lg:px-10">
      <DataState
        isPending={site.isPending}
        isError={site.isError}
        error={site.error}
        loadingLabel="Loading site performance…"
      >
        {site.data && (
          <>
            <PageHeader
              breadcrumbs={[
                { label: "Organization", href: "/performance/organization" },
                { label: "Sites", href: "/performance/sites" },
                { label: site.data.site_name },
              ]}
              title={site.data.site_name}
              description={`${site.data.site_code} · ${site.data.asset_count} monitored asset${site.data.asset_count === 1 ? "" : "s"}`}
              actions={
                <>
                  <ProvenanceBadge value={site.data.provenance} />
                  <span className="text-xs text-zinc-400 dark:text-zinc-600">
                    as of <RelativeTime iso={site.data.as_of} />
                  </span>
                  <Link
                    href={`/fleet?site=${site.data.site_id}`}
                    className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  >
                    View this site&rsquo;s fleet →
                  </Link>
                </>
              }
            />

            {/* Compact top summary — site/asset count, areas, attention, maintenance,
                evidence limitations (Enterprise Product Rebuild Pass 2 §4) — the
                deep-dive views live behind the tabs below, not repeated here. */}
            <div className="flex flex-wrap gap-x-8 gap-y-2 border-y border-zinc-100 py-3 text-sm dark:border-zinc-800/70">
              <div>
                <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                  {siteAreas.length}
                </span>{" "}
                <span className="text-zinc-500 dark:text-zinc-400">areas</span>
              </div>
              <div>
                <span
                  className={`font-semibold ${site.data.critical_attention_count > 0 ? "text-red-600 dark:text-red-400" : "text-zinc-900 dark:text-zinc-100"}`}
                >
                  {site.data.attention_count}
                </span>{" "}
                <span className="text-zinc-500 dark:text-zinc-400">
                  need attention ({site.data.critical_attention_count} critical)
                </span>
              </div>
              <div>
                <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                  {site.data.open_maintenance_actions}
                </span>{" "}
                <span className="text-zinc-500 dark:text-zinc-400">open maintenance</span>
              </div>
              <div>
                <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                  {dataTrustLimited}
                </span>{" "}
                <span className="text-zinc-500 dark:text-zinc-400">evidence limitations</span>
              </div>
            </div>

            <WorkspaceTabs tabs={SITE_TABS} active={view} onChange={setView} />

            {view === "overview" && (
              <div className="flex flex-col gap-6">
                <ConditionBreakdown distribution={site.data.condition_distribution} />
                <SectionCard title="Areas at this site">
                  <DataState
                    isPending={areas.isPending}
                    isError={areas.isError}
                    error={areas.error}
                  >
                    <AreaPerformanceTable areas={siteAreas} currentSiteCode={site.data.site_code} />
                  </DataState>
                </SectionCard>
                <PortfolioAttentionQueue
                  assets={site.data.top_attention_assets.slice(0, 5)}
                  showSite={false}
                />
              </div>
            )}

            {view === "reliability" && (
              <div className="flex flex-col gap-6">
                <ConditionBreakdown distribution={site.data.condition_distribution} />
                <PortfolioAttentionQueue assets={site.data.top_attention_assets} showSite={false} />
              </div>
            )}

            {view === "maintenance" && (
              <div className="grid gap-6 lg:grid-cols-2">
                <MaintenanceOutcomesPanel
                  distribution={site.data.open_maintenance_outcome_distribution}
                  openActions={site.data.open_maintenance_actions}
                />
                <ActionReadinessPanel distribution={site.data.action_readiness_distribution} />
              </div>
            )}

            {view === "energy" && (
              <div className="flex flex-col gap-6">
                <EnergyEfficiencyPanel
                  activeOpportunities={site.data.active_energy_opportunities}
                  attributionSupportedOpportunities={site.data.attribution_supported_opportunities}
                  qualifiedRecoveryCount={site.data.qualified_recovery_count}
                  qualifiedAvoidedEnergyKwhTotal={site.data.qualified_avoided_energy_kwh_total}
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {site.data.energy_assessable_assets} of {site.data.asset_count} monitored assets
                  at this site are currently energy-assessable.
                </p>
                <CarbonPanel
                  estimatedCo2eKgTotal={site.data.estimated_co2e_kg_total}
                  qualifyingOutcomeCount={site.data.carbon_estimate_available_count}
                />
              </div>
            )}

            {view === "data-trust" && (
              <DataTrustPanel distribution={site.data.data_trust_distribution} />
            )}

            {view === "outcomes" && (
              <PortfolioRecentOutcomes outcomes={site.data.recent_outcomes} />
            )}
          </>
        )}
      </DataState>
    </div>
  );
}
