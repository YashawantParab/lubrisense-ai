import Link from "next/link";

import { PortfolioOutcomeBadge, ProvenanceBadge } from "@/components/badges";
import { EmptyState } from "@/components/empty-state";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import type { RecentOutcome } from "@/lib/api/performance-types";

/**
 * Typed, differentiated outcome feed (task §14) — condition resolution, maintenance
 * completion, energy recovery, and carbon estimation are visually distinguished (badge +
 * summary text) rather than presented as interchangeable events. `summary` and
 * `provenance` are both backend-authored strings — this component renders them, it never
 * derives its own.
 */
export function PortfolioRecentOutcomes({ outcomes }: { outcomes: RecentOutcome[] }) {
  return (
    <SectionCard title="Recent outcomes">
      {outcomes.length === 0 ? (
        <EmptyState
          title="No outcomes yet"
          description="Outcomes appear here once a condition resolves, a maintenance case completes, an energy recovery is qualified, or a carbon estimate is produced."
        />
      ) : (
        <ul className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
          {outcomes.map((outcome, index) => (
            <li
              key={`${outcome.ref.machine_id}-${outcome.outcome_type}-${index}`}
              className="flex flex-wrap items-center justify-between gap-2 py-2.5"
            >
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <PortfolioOutcomeBadge value={outcome.outcome_type} />
                  <Link
                    href={`/machines/${outcome.ref.machine_id}`}
                    className="text-sm font-medium text-sky-700 hover:underline dark:text-sky-400"
                  >
                    {outcome.ref.name}
                  </Link>
                </div>
                <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{outcome.summary}</p>
              </div>
              <div className="flex items-center gap-2">
                <ProvenanceBadge value={outcome.provenance} />
                <RelativeTime
                  iso={outcome.occurred_at}
                  className="text-xs text-zinc-400 dark:text-zinc-600"
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
