"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { PortfolioAttentionQueue } from "@/components/portfolio/portfolio-attention-queue";
import { usePageTitle } from "@/hooks/use-page-title";
import { useAttentionQueue } from "@/hooks/use-performance";

type PriorityFilter = "all" | "reliability" | "critical" | "data-limited";

const FILTER_LABEL: Record<PriorityFilter, string> = {
  all: "All",
  reliability: "Reliability risk",
  critical: "Critical only",
  "data-limited": "Data limited",
};

// Presentation-only filtering of an already-fetched, backend-computed priority field —
// never a re-derivation of priority itself (Enterprise Product Rebuild §2/§3): the
// Organization KPI strip's "Need attention"/"Critical attention" counts only reconcile
// with this page if the destination can be filtered to the exact same real subset.
const FILTER_MATCH: Record<PriorityFilter, (priority: string) => boolean> = {
  all: () => true,
  reliability: (p) => p === "ATTENTION" || p === "HIGH_ATTENTION" || p === "CRITICAL_ATTENTION",
  critical: (p) => p === "CRITICAL_ATTENTION",
  "data-limited": (p) => p === "DATA_LIMITED",
};

export default function AttentionQueuePage() {
  return (
    <Suspense fallback={null}>
      <AttentionQueuePageContent />
    </Suspense>
  );
}

function AttentionQueuePageContent() {
  usePageTitle("Priority Attention");
  const attention = useAttentionQueue(200);
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filter = (searchParams.get("priority") as PriorityFilter | null) ?? "all";
  const setFilter = (value: PriorityFilter) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === "all") params.delete("priority");
    else params.set("priority", value);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const filtered = useMemo(
    () => (attention.data ?? []).filter((a) => FILTER_MATCH[filter](a.priority)),
    [attention.data, filter],
  );

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        breadcrumbs={[{ label: "Organization", href: "/performance/organization" }]}
        title="Priority attention"
        description="Every monitored asset the backend's deterministic priority policy currently ranks above monitoring-only — reliability and safety evidence always outranks energy/carbon evidence."
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 rounded-md border border-zinc-300 p-0.5 text-xs dark:border-zinc-700">
          {(Object.keys(FILTER_LABEL) as PriorityFilter[]).map((key) => (
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
          {filtered.length} of {(attention.data ?? []).length} assets
        </span>
      </div>

      <DataState
        isPending={attention.isPending}
        isError={attention.isError}
        error={attention.error}
        loadingLabel="Loading priority attention…"
      >
        <PortfolioAttentionQueue assets={filtered} />
      </DataState>
    </div>
  );
}
