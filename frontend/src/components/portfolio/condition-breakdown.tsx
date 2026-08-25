import { SectionCard } from "@/components/section-card";
import { SegmentedDistributionBar } from "@/components/segmented-distribution-bar";
import { humanize } from "@/lib/terminology";
import { toDynamicSegments } from "@/lib/portfolio";

/** Site/area responses expose the raw, open-vocabulary `condition_distribution` rather
 * than the organization's fixed priority buckets (`ReliabilityPanel`) — this renders that
 * dynamic map without inventing a fixed category set the backend didn't provide. */
export function ConditionBreakdown({
  distribution,
  title = "Condition breakdown",
}: {
  distribution: Record<string, number>;
  title?: string;
}) {
  return (
    <SectionCard title={title}>
      <SegmentedDistributionBar
        segments={toDynamicSegments(distribution, humanize)}
        emptyLabel="No condition assessments recorded yet."
      />
    </SectionCard>
  );
}
