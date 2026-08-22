"use client";

import Link from "next/link";

import { SectionCard } from "@/components/section-card";
import { useQualitySummary } from "@/hooks/use-data-quality";
import { useFleetLatestConditions } from "@/hooks/use-intelligence";
import { fleetBucket } from "@/lib/fleet-condition";

/** CLAUDE.md §8 — makes Data Quality meaningful on Overview without forcing a reviewer
 * into the Engineering page. Every number is read directly from the tenant-wide quality
 * summary + the same fleet-latest condition buckets the distribution chart uses — no
 * separate computation invented for this card. */
export function DataTrustSummary() {
  const summary = useQualitySummary();
  const conditions = useFleetLatestConditions();

  const trusted = summary.data?.sensors_by_quality_state?.TRUSTED ?? 0;
  const needsAttention =
    (summary.data?.sensors_by_quality_state?.USABLE_WITH_CAUTION ?? 0) +
    (summary.data?.sensors_by_quality_state?.UNUSABLE ?? 0);
  const insufficientEvidenceAssets = (conditions.data ?? []).filter(
    (c) => fleetBucket(c) === "insufficient_evidence" || fleetBucket(c) === "data_quality",
  ).length;

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
      <dl className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-zinc-500 dark:text-zinc-400">Trusted sensors</dt>
          <dd className="text-lg font-medium text-emerald-600 dark:text-emerald-400">{trusted}</dd>
        </div>
        <div>
          <dt className="text-zinc-500 dark:text-zinc-400">Sensors needing attention</dt>
          <dd className="text-lg font-medium text-amber-600 dark:text-amber-400">
            {needsAttention}
          </dd>
        </div>
        <div>
          <dt className="text-zinc-500 dark:text-zinc-400">Assets with limited evidence</dt>
          <dd className="text-lg font-medium text-zinc-700 dark:text-zinc-300">
            {insufficientEvidenceAssets}
          </dd>
        </div>
      </dl>
    </SectionCard>
  );
}
