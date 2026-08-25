"use client";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { PortfolioAttentionQueue } from "@/components/portfolio/portfolio-attention-queue";
import { usePageTitle } from "@/hooks/use-page-title";
import { useAttentionQueue } from "@/hooks/use-performance";

export default function AttentionQueuePage() {
  usePageTitle("Priority Attention");
  const attention = useAttentionQueue(200);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        breadcrumbs={[{ label: "Organization", href: "/performance/organization" }]}
        title="Priority attention"
        description="Every monitored asset the backend's deterministic priority policy currently ranks above monitoring-only — reliability and safety evidence always outranks energy/carbon evidence."
      />
      <DataState
        isPending={attention.isPending}
        isError={attention.isError}
        error={attention.error}
        loadingLabel="Loading priority attention…"
      >
        <PortfolioAttentionQueue assets={attention.data ?? []} />
      </DataState>
    </div>
  );
}
