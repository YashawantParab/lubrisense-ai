"use client";

import { AreaPerformanceTable } from "@/components/portfolio/area-performance-table";
import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { usePageTitle } from "@/hooks/use-page-title";
import { useAreaPerformances } from "@/hooks/use-performance";

export default function AreasPerformancePage() {
  usePageTitle("Areas");
  const areas = useAreaPerformances();

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        breadcrumbs={[{ label: "Organization", href: "/performance/organization" }]}
        title="Areas"
        description="Process areas from real seeded machine metadata, organization-wide — an area active at more than one site shows a combined total, never a fabricated per-site split."
      />
      <DataState
        isPending={areas.isPending}
        isError={areas.isError}
        error={areas.error}
        loadingLabel="Loading areas…"
      >
        <AreaPerformanceTable areas={areas.data ?? []} />
      </DataState>
    </div>
  );
}
