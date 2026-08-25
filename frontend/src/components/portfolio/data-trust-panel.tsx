import Link from "next/link";

import { SectionCard } from "@/components/section-card";
import { SegmentedDistributionBar } from "@/components/segmented-distribution-bar";
import { humanize } from "@/lib/terminology";
import { DATA_TRUST_BAR_CLASS, DATA_TRUST_ORDER, toSegments } from "@/lib/portfolio";

/** Deliberately not "X% sensors healthy" (CLAUDE.md §13) — a decision-evidence-trust
 * category per machine, plus a standalone critical-asset-limited count that stays visible
 * even when the overall distribution looks mostly trusted. */
export function DataTrustPanel({
  distribution,
  criticalAssetsLimited,
}: {
  distribution: Record<string, number>;
  criticalAssetsLimited?: number;
}) {
  return (
    <SectionCard
      title="Data trust"
      actions={
        <Link
          href="/data-quality"
          className="text-xs text-sky-600 hover:underline dark:text-sky-400"
        >
          View data quality
        </Link>
      }
    >
      {criticalAssetsLimited !== undefined && criticalAssetsLimited > 0 && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
          {criticalAssetsLimited} critical asset{criticalAssetsLimited === 1 ? "" : "s"} currently
          {criticalAssetsLimited === 1 ? " has" : " have"} limited decision evidence — this stays
          visible regardless of how trusted the rest of the fleet&apos;s sensors are.
        </div>
      )}
      <SegmentedDistributionBar
        segments={toSegments(distribution, DATA_TRUST_ORDER, DATA_TRUST_BAR_CLASS, humanize)}
        emptyLabel="No assets assessed yet."
      />
    </SectionCard>
  );
}
