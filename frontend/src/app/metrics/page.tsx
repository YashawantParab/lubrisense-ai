"use client";

import { ProvenanceBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { usePageTitle } from "@/hooks/use-page-title";
import { useProductMetrics } from "@/hooks/use-product-metrics";
import type { MetricResponse } from "@/lib/api/product-metrics-types";

function formatValue(metric: MetricResponse): string {
  if (metric.value === null) return "Not enough data";
  if (metric.unit === "ratio") return `${Math.round(metric.value * 100)}%`;
  return `${Math.round(metric.value * 100) / 100} ${metric.unit}`;
}

const GROUPS: { label: string; prefixes: string[] }[] = [
  { label: "Coverage", prefixes: ["coverage."] },
  { label: "Detection quality", prefixes: ["feedback.", "decisions."] },
  { label: "Workflow", prefixes: ["workflow.", "maintenance."] },
  { label: "Service burden", prefixes: ["incidents."] },
  { label: "Knowledge / Assistant", prefixes: ["assistant.", "knowledge."] },
];

function groupFor(metricId: string): string {
  const group = GROUPS.find((g) => g.prefixes.some((p) => metricId.startsWith(p)));
  return group?.label ?? "Other";
}

function MetricCard({ metric }: { metric: MetricResponse }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{metric.name}</h3>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{metric.definition}</p>
        </div>
        <ProvenanceBadge value={metric.provenance} />
      </div>
      <div className="mt-3 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
        {formatValue(metric)}
      </div>
      <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        {metric.window_description}
        {metric.data_completeness_note && (
          <span className="block text-amber-600 dark:text-amber-400">
            {metric.data_completeness_note}
          </span>
        )}
      </div>
    </div>
  );
}

export default function MetricsPage() {
  usePageTitle("Metrics");
  const metrics = useProductMetrics();

  const grouped = (metrics.data?.supporting ?? []).reduce<Record<string, MetricResponse[]>>(
    (acc, metric) => {
      const group = groupFor(metric.metric_id);
      (acc[group] ??= []).push(metric);
      return acc;
    },
    {},
  );

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Product Metrics"
        description="The North Star and supporting metrics, each with explicit provenance — measured, demo estimate, or configured target — never mixed silently into one number."
      />

      <DataState isPending={metrics.isPending} isError={metrics.isError} error={metrics.error}>
        {metrics.data && (
          <div className="flex flex-col gap-6">
            <SectionCard title="North Star">
              <MetricCard metric={metrics.data.north_star} />
            </SectionCard>

            {GROUPS.map((group) =>
              grouped[group.label]?.length ? (
                <SectionCard key={group.label} title={group.label}>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {grouped[group.label].map((metric) => (
                      <MetricCard key={metric.metric_id} metric={metric} />
                    ))}
                  </div>
                </SectionCard>
              ) : null,
            )}
          </div>
        )}
      </DataState>
    </div>
  );
}
