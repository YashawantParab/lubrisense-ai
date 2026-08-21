"use client";

import { useMemo } from "react";

import { SectionCard } from "@/components/section-card";
import { useFleetLatestConditions } from "@/hooks/use-intelligence";
import { FLEET_BUCKET_LABELS, fleetBucket, type FleetBucket } from "@/lib/fleet-condition";

const BUCKET_ORDER: FleetBucket[] = ["healthy", "attention", "recovering", "data_quality", "insufficient_evidence"];

// Matches the product's existing severity/tone vocabulary (terminology.ts): teal/emerald
// for confidently normal, amber for something to look at, sky for a positive trend in
// progress, zinc for a structural (not severity) limitation.
const BUCKET_BAR_CLASSES: Record<FleetBucket, string> = {
  healthy: "bg-emerald-500",
  attention: "bg-amber-500",
  recovering: "bg-sky-500",
  data_quality: "bg-zinc-400 dark:bg-zinc-500",
  insufficient_evidence: "bg-zinc-300 dark:bg-zinc-600",
};

/** One useful fleet-wide chart (CLAUDE.md §5) — instant portfolio comprehension, not a
 * decorative graphic. Every count is a real bucketed tally of persisted, latest-per-
 * machine condition assessments (`fleetBucket`), never fabricated proportions. */
export function FleetConditionDistribution() {
  const conditions = useFleetLatestConditions();

  const counts = useMemo(() => {
    const tally: Record<FleetBucket, number> = {
      healthy: 0,
      attention: 0,
      recovering: 0,
      data_quality: 0,
      insufficient_evidence: 0,
    };
    for (const condition of conditions.data ?? []) {
      tally[fleetBucket(condition)] += 1;
    }
    return tally;
  }, [conditions.data]);

  const total = BUCKET_ORDER.reduce((sum, bucket) => sum + counts[bucket], 0);

  return (
    <SectionCard title="Fleet by condition">
      {total === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No condition assessments recorded yet.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
            {BUCKET_ORDER.filter((bucket) => counts[bucket] > 0).map((bucket) => (
              <div
                key={bucket}
                className={BUCKET_BAR_CLASSES[bucket]}
                style={{ width: `${(counts[bucket] / total) * 100}%` }}
                title={`${FLEET_BUCKET_LABELS[bucket]}: ${counts[bucket]}`}
              />
            ))}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
            {BUCKET_ORDER.map((bucket) => (
              <div key={bucket} className="flex items-center gap-2 text-sm">
                <span className={`h-2 w-2 shrink-0 rounded-full ${BUCKET_BAR_CLASSES[bucket]}`} />
                <dt className="text-zinc-500 dark:text-zinc-400">{FLEET_BUCKET_LABELS[bucket]}</dt>
                <dd className="ml-auto font-medium text-zinc-900 dark:text-zinc-100">
                  {counts[bucket]}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </SectionCard>
  );
}
