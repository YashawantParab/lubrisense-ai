"use client";

import { use } from "react";
import Link from "next/link";

import { DataState } from "@/components/data-state";
import { ProvenanceBadge } from "@/components/badges";
import { KpiStrip } from "@/components/kpi-strip";
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
import { usePageTitle } from "@/hooks/use-page-title";
import { useAreaPerformances, useSitePerformance } from "@/hooks/use-performance";

export default function SiteDetailPage({ params }: { params: Promise<{ siteId: string }> }) {
  const { siteId } = use(params);
  const site = useSitePerformance(siteId);
  const areas = useAreaPerformances();

  usePageTitle(site.data?.site_name ?? "Site");

  const siteAreas = (areas.data ?? []).filter((area) =>
    area.site_codes.includes(site.data?.site_code ?? "__none__"),
  );

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-10 px-6 py-10 lg:px-10">
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

            <KpiStrip
              items={[
                { label: "Need attention", value: site.data.attention_count },
                {
                  label: "Critical attention",
                  value: site.data.critical_attention_count,
                  valueClassName:
                    site.data.critical_attention_count > 0
                      ? "text-red-600 dark:text-red-400"
                      : undefined,
                },
                { label: "Active incidents", value: site.data.active_incidents },
                { label: "Open maintenance", value: site.data.open_maintenance_actions },
                {
                  label: "Energy opportunities",
                  value: site.data.active_energy_opportunities,
                },
                {
                  label: "Qualified recoveries",
                  value: site.data.qualified_recovery_count,
                  valueClassName:
                    site.data.qualified_recovery_count > 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : undefined,
                },
              ]}
            />

            <ConditionBreakdown
              distribution={site.data.condition_distribution}
              title="Condition breakdown"
            />

            <SectionCard title="Areas at this site">
              <DataState isPending={areas.isPending} isError={areas.isError} error={areas.error}>
                <AreaPerformanceTable areas={siteAreas} currentSiteCode={site.data.site_code} />
              </DataState>
            </SectionCard>

            <PortfolioAttentionQueue assets={site.data.top_attention_assets} showSite={false} />

            <EnergyEfficiencyPanel
              activeOpportunities={site.data.active_energy_opportunities}
              attributionSupportedOpportunities={site.data.attribution_supported_opportunities}
              qualifiedRecoveryCount={site.data.qualified_recovery_count}
              qualifiedAvoidedEnergyKwhTotal={site.data.qualified_avoided_energy_kwh_total}
            />

            <CarbonPanel
              estimatedCo2eKgTotal={site.data.estimated_co2e_kg_total}
              qualifyingOutcomeCount={site.data.carbon_estimate_available_count}
            />

            <div className="grid gap-6 lg:grid-cols-2">
              <MaintenanceOutcomesPanel
                distribution={site.data.open_maintenance_outcome_distribution}
                openActions={site.data.open_maintenance_actions}
              />
              <ActionReadinessPanel distribution={site.data.action_readiness_distribution} />
            </div>

            <DataTrustPanel distribution={site.data.data_trust_distribution} />

            <PortfolioRecentOutcomes outcomes={site.data.recent_outcomes} />
          </>
        )}
      </DataState>
    </div>
  );
}
