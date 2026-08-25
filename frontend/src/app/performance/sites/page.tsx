"use client";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { SitePerformanceTable } from "@/components/portfolio/site-performance-table";
import { usePageTitle } from "@/hooks/use-page-title";
import { useSitePerformances } from "@/hooks/use-performance";

export default function SitesPerformancePage() {
  usePageTitle("Sites");
  const sites = useSitePerformances();

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        breadcrumbs={[{ label: "Organization", href: "/performance/organization" }]}
        title="Sites"
        description="Every monitored site, ranked by critical attention then attention — click through for site-level reliability, maintenance, energy, and data-trust detail."
      />
      <DataState
        isPending={sites.isPending}
        isError={sites.isError}
        error={sites.error}
        loadingLabel="Loading sites…"
      >
        <SitePerformanceTable sites={sites.data ?? []} />
      </DataState>
    </div>
  );
}
