import Link from "next/link";

import { SectionCard } from "@/components/section-card";
import { SegmentedDistributionBar } from "@/components/segmented-distribution-bar";
import { humanize } from "@/lib/terminology";
import {
  MAINTENANCE_OUTCOME_BAR_CLASS,
  MAINTENANCE_OUTCOME_ORDER,
  toSegments,
} from "@/lib/portfolio";

export interface MaintenanceOutcomesPanelProps {
  distribution: Record<string, number>;
  openActions?: number;
  overdueActions?: number;
}

/** A completed maintenance case is never rendered as an automatic success — the
 * distribution always differentiates open work from every completed-outcome tier
 * (qualified recovery / probable recovery / no material change / inconclusive /
 * deteriorated), per CLAUDE.md's maintenance-workflow discipline. */
export function MaintenanceOutcomesPanel({
  distribution,
  openActions,
  overdueActions,
}: MaintenanceOutcomesPanelProps) {
  return (
    <SectionCard
      title="Maintenance performance"
      actions={
        <Link
          href="/maintenance"
          className="text-xs text-sky-600 hover:underline dark:text-sky-400"
        >
          View maintenance
        </Link>
      }
    >
      {(openActions !== undefined || overdueActions !== undefined) && (
        <div className="mb-4 flex flex-wrap gap-x-8 gap-y-2 text-sm">
          {openActions !== undefined && (
            <div>
              <span className="font-semibold text-zinc-900 dark:text-zinc-100">{openActions}</span>{" "}
              <span className="text-zinc-500 dark:text-zinc-400">open actions</span>
            </div>
          )}
          {overdueActions !== undefined && overdueActions > 0 && (
            <div>
              <span className="font-semibold text-amber-600 dark:text-amber-400">
                {overdueActions}
              </span>{" "}
              <span className="text-zinc-500 dark:text-zinc-400">overdue</span>
            </div>
          )}
        </div>
      )}
      <SegmentedDistributionBar
        segments={toSegments(
          distribution,
          MAINTENANCE_OUTCOME_ORDER,
          MAINTENANCE_OUTCOME_BAR_CLASS,
          humanize,
        )}
        emptyLabel="No maintenance actions recorded yet."
      />
    </SectionCard>
  );
}
