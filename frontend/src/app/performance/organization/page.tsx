"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { DataState } from "@/components/data-state";
import { ActionReadinessPanel } from "@/components/portfolio/action-readiness-panel";
import { CarbonPanel } from "@/components/portfolio/carbon-panel";
import { DataTrustPanel } from "@/components/portfolio/data-trust-panel";
import { DecisionGroups } from "@/components/portfolio/decision-groups";
import { EnergyEfficiencyPanel } from "@/components/portfolio/energy-efficiency-panel";
import { MaintenanceOutcomesPanel } from "@/components/portfolio/maintenance-outcomes-panel";
import { OrganizationHeader } from "@/components/portfolio/organization-header";
import { PortfolioAttentionQueue } from "@/components/portfolio/portfolio-attention-queue";
import { PortfolioRecentOutcomes } from "@/components/portfolio/portfolio-recent-outcomes";
import { ReliabilityPanel } from "@/components/portfolio/reliability-panel";
import { SitePerformanceTable } from "@/components/portfolio/site-performance-table";
import { SectionCard } from "@/components/section-card";
import { WorkspaceTabs } from "@/components/workspace-tabs";
import { usePageTitle } from "@/hooks/use-page-title";
import { useOrganizationPerformance, useSitePerformances } from "@/hooks/use-performance";

type WorkspaceView = "health" | "maintenance" | "energy" | "data-trust";

const WORKSPACE_TABS: { key: WorkspaceView; label: string }[] = [
  { key: "health", label: "Health & Attention" },
  { key: "maintenance", label: "Maintenance" },
  { key: "energy", label: "Energy & Efficiency" },
  { key: "data-trust", label: "Data Trust" },
];

export default function OrganizationPerformancePage() {
  return (
    <Suspense fallback={null}>
      <OrganizationPerformancePageContent />
    </Suspense>
  );
}

function OrganizationPerformancePageContent() {
  usePageTitle("Organization");
  const org = useOrganizationPerformance();
  const sites = useSitePerformances();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const view = (searchParams.get("view") as WorkspaceView | null) ?? "health";
  const setView = (value: WorkspaceView) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === "health") params.delete("view");
    else params.set("view", value);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const dataTrustLimited =
    (org.data?.data_trust.distribution["ASSESSMENT_BLOCKED"] ?? 0) +
    (org.data?.data_trust.distribution["ACTION_BLOCKED"] ?? 0);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-8 px-6 py-10 lg:px-10">
      <DataState
        isPending={org.isPending}
        isError={org.isError}
        error={org.error}
        loadingLabel="Loading organization performance…"
      >
        {org.data && (
          <>
            <OrganizationHeader
              organizationName={org.data.organization_name}
              asOf={org.data.as_of}
              sites={org.data.portfolio.sites}
              monitoredAssets={org.data.portfolio.monitored_assets}
              provenance={org.data.provenance}
            />

            <DecisionGroups
              reliability={[
                {
                  label: "Need attention",
                  value: org.data.reliability.attention_assets,
                  href: "/performance/attention?priority=reliability",
                },
                {
                  label: "Critical attention",
                  value: org.data.reliability.critical_attention_assets,
                  valueClassName:
                    org.data.reliability.critical_attention_assets > 0
                      ? "text-red-600 dark:text-red-400"
                      : undefined,
                  href: "/performance/attention?priority=critical",
                },
                {
                  label: "Evidence limitations",
                  value: dataTrustLimited,
                  href: "/data-quality",
                },
              ]}
              maintenance={[
                {
                  label: "Open maintenance actions",
                  value: org.data.maintenance.open_actions,
                  href: "/maintenance?state=open",
                },
                {
                  label: "Overdue",
                  value: org.data.maintenance.overdue_actions,
                  valueClassName:
                    org.data.maintenance.overdue_actions > 0
                      ? "text-amber-600 dark:text-amber-400"
                      : undefined,
                  href: "/maintenance?state=open",
                },
                {
                  label: "Qualified recoveries",
                  value: org.data.energy_efficiency.qualified_recovery_count,
                  valueClassName:
                    org.data.energy_efficiency.qualified_recovery_count > 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : undefined,
                  href: "/energy?status=qualified",
                },
              ]}
              efficiency={[
                {
                  label: "Energy assessable",
                  value: `${org.data.energy_efficiency.energy_assessable_assets} / ${org.data.portfolio.monitored_assets}`,
                  href: "/energy",
                },
                {
                  label: "Active energy opportunities",
                  value: org.data.energy_efficiency.active_opportunities,
                  href: "/energy?status=opportunity",
                },
                {
                  label: "Estimated CO2e (qualified)",
                  value: `${org.data.carbon.estimated_co2e_kg_total.toFixed(1)} kg`,
                  href: "/energy?status=qualified",
                },
              ]}
            />

            <section className="flex flex-col gap-4">
              <WorkspaceTabs tabs={WORKSPACE_TABS} active={view} onChange={setView} />

              {view === "health" && (
                <div className="flex flex-col gap-6">
                  <ReliabilityPanel distribution={org.data.reliability.priority_distribution} />
                  <SectionCard
                    title="Site performance"
                    actions={
                      <Link
                        href="/performance/sites"
                        className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                      >
                        View all sites
                      </Link>
                    }
                  >
                    <DataState
                      isPending={sites.isPending}
                      isError={sites.isError}
                      error={sites.error}
                    >
                      <SitePerformanceTable sites={sites.data ?? []} />
                    </DataState>
                  </SectionCard>
                </div>
              )}

              {view === "maintenance" && (
                <div className="grid gap-6 lg:grid-cols-2">
                  <MaintenanceOutcomesPanel
                    distribution={org.data.maintenance.outcome_distribution}
                    openActions={org.data.maintenance.open_actions}
                    overdueActions={org.data.maintenance.overdue_actions}
                  />
                  <ActionReadinessPanel distribution={org.data.action_readiness.distribution} />
                </div>
              )}

              {view === "energy" && (
                <div className="flex flex-col gap-6">
                  <EnergyEfficiencyPanel
                    distribution={org.data.energy_efficiency.distribution}
                    activeOpportunities={org.data.energy_efficiency.active_opportunities}
                    attributionSupportedOpportunities={
                      org.data.energy_efficiency.attribution_supported_opportunities
                    }
                    qualifiedRecoveryCount={org.data.energy_efficiency.qualified_recovery_count}
                    qualifiedAvoidedEnergyKwhTotal={
                      org.data.energy_efficiency.qualified_avoided_energy_kwh_total
                    }
                  />
                  <CarbonPanel
                    estimatedCo2eKgTotal={org.data.carbon.estimated_co2e_kg_total}
                    qualifyingOutcomeCount={org.data.carbon.carbon_estimate_available_count}
                    missingFactorCount={org.data.carbon.carbon_outcomes_missing_factor}
                  />
                </div>
              )}

              {view === "data-trust" && (
                <DataTrustPanel
                  distribution={org.data.data_trust.distribution}
                  criticalAssetsLimited={org.data.data_trust.critical_assets_limited}
                />
              )}
            </section>

            <PortfolioAttentionQueue
              assets={org.data.top_attention_assets}
              actions={
                <Link
                  href="/performance/attention"
                  className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                >
                  View full queue
                </Link>
              }
            />

            <PortfolioRecentOutcomes outcomes={org.data.recent_outcomes} />

            <p className="text-xs text-zinc-400 dark:text-zinc-600">
              Looking for the asset-level condition-driven walkthrough?{" "}
              <Link href="/overview" className="text-sky-600 hover:underline dark:text-sky-400">
                See the fleet overview →
              </Link>
            </p>
          </>
        )}
      </DataState>
    </div>
  );
}
