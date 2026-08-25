import { SectionCard } from "@/components/section-card";
import { SegmentedDistributionBar } from "@/components/segmented-distribution-bar";
import { humanize } from "@/lib/terminology";
import { PRIORITY_BAR_CLASS, PRIORITY_ORDER, toSegments } from "@/lib/portfolio";

/** The organization's single strongest reliability visualization (task §4) — the same
 * deterministic, versioned `PortfolioPriority` categories the attention queue itself uses
 * to rank assets, not a separately invented health score. */
export function ReliabilityPanel({ distribution }: { distribution: Record<string, number> }) {
  return (
    <SectionCard title="Fleet reliability state">
      <SegmentedDistributionBar
        segments={toSegments(distribution, PRIORITY_ORDER, PRIORITY_BAR_CLASS, humanize)}
        emptyLabel="No condition assessments recorded yet."
      />
    </SectionCard>
  );
}
