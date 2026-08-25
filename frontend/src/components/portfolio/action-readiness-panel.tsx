import Link from "next/link";

import { SectionCard } from "@/components/section-card";
import { SegmentedDistributionBar } from "@/components/segmented-distribution-bar";
import { humanize } from "@/lib/terminology";
import { ACTION_READINESS_BAR_CLASS, ACTION_READINESS_ORDER, toSegments } from "@/lib/portfolio";

/** This reference architecture has no automated-control or safety-interlock subsystem —
 * every action always requires human review (CLAUDE.md's Workflow Intelligence
 * boundary), which is exactly why the backend's `ActionReadinessState` vocabulary has no
 * "auto-eligible"/"safety-interlock-blocked" values to render here. */
export function ActionReadinessPanel({ distribution }: { distribution: Record<string, number> }) {
  return (
    <SectionCard
      title="Action readiness"
      actions={
        <Link
          href="/action-readiness"
          className="text-xs text-sky-600 hover:underline dark:text-sky-400"
        >
          View action readiness
        </Link>
      }
    >
      <SegmentedDistributionBar
        segments={toSegments(
          distribution,
          ACTION_READINESS_ORDER,
          ACTION_READINESS_BAR_CLASS,
          humanize,
        )}
        emptyLabel="No assets assessed yet."
      />
    </SectionCard>
  );
}
