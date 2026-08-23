import { StatusPill } from "@/components/status-pill";
import {
  FUSION_STRENGTH_LABEL,
  FUSION_STRENGTH_TONE,
  type FusionStrength,
} from "@/lib/evidence-fusion";

export interface FusionSource {
  label: string;
  strength: FusionStrength;
}

/** Visual "how did we get here" chain for one machine's current condition (ML
 * productization pass, item 10): the real evidence sources that fed
 * `ConditionEngine.assess`, each labeled with its real contribution strength, flowing into
 * the condition it produced and (optionally) the decision/action-readiness that followed.
 * Every value passed in is already-persisted product state — this component only lays it
 * out, it never computes or guesses a strength itself. */
export function EvidenceFusionDiagram({
  sources,
  conditionLabel,
  decisionLabel,
  actionReadinessLabel,
}: {
  sources: FusionSource[];
  conditionLabel: string;
  decisionLabel?: string | null;
  actionReadinessLabel?: string | null;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-2 sm:grid-cols-4">
        {sources.map((source) => (
          <div
            key={source.label}
            className="rounded-md border border-zinc-200 p-2.5 dark:border-zinc-800"
          >
            <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400">{source.label}</p>
            <div className="mt-1.5">
              <StatusPill tone={FUSION_STRENGTH_TONE[source.strength]}>
                {FUSION_STRENGTH_LABEL[source.strength]}
              </StatusPill>
            </div>
          </div>
        ))}
      </div>
      <p className="text-center text-xs text-zinc-400 dark:text-zinc-600" aria-hidden>
        ↓ fused into ↓
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2 text-sm">
        <span className="rounded-md bg-zinc-100 px-3 py-1.5 font-medium text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
          {conditionLabel}
        </span>
        {decisionLabel != null && (
          <>
            <span className="text-zinc-300 dark:text-zinc-700" aria-hidden>
              →
            </span>
            <span className="rounded-md bg-zinc-100 px-3 py-1.5 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              {decisionLabel}
            </span>
          </>
        )}
        {actionReadinessLabel != null && (
          <>
            <span className="text-zinc-300 dark:text-zinc-700" aria-hidden>
              →
            </span>
            <span className="rounded-md bg-sky-50 px-3 py-1.5 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400">
              {actionReadinessLabel}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
