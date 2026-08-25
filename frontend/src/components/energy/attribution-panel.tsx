import { AttributionLevelBadge } from "@/components/badges";
import { formatPct } from "@/lib/energy-format";
import { qualityLabel, qualityTone } from "@/lib/terminology";
import { StatusPill } from "@/components/status-pill";
import type { Attribution } from "@/lib/api/energy-types";

function EvidenceList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{title}</p>
      <ul className="mt-1 list-inside list-disc text-sm text-zinc-700 dark:text-zinc-300">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Lubrication attribution, kept visually separate from the energy-deviation figure it's
 * evaluating (task §8) — a two-panel layout, never one merged statement, so a reader can
 * never read "+13.7%" as if it were itself a lubrication claim. `attribution_level` is
 * evidence-strength language (NO_EVIDENCE/POSSIBLE/MODERATE/STRONG), never a numeric
 * causal percentage — this component renders exactly that vocabulary, nothing stronger.
 */
export function AttributionPanel({ attribution }: { attribution: Attribution }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5 rounded-lg bg-zinc-50/70 p-4 dark:bg-zinc-900/40">
        <p className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
          Energy deviation
        </p>
        <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          {formatPct(attribution.energy_residual_pct)}
        </p>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Observed deviation from contextual expectation — a physical measurement, not yet a
          lubrication claim.
        </p>
      </div>

      <div className="flex flex-col gap-1.5 rounded-lg bg-amber-50/60 p-4 dark:bg-amber-500/[0.06]">
        <p className="text-xs font-semibold tracking-wide text-amber-700 uppercase dark:text-amber-400">
          Lubrication attribution
        </p>
        <div>
          <AttributionLevelBadge value={attribution.attribution_level} />
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          How strongly independent evidence supports lubrication condition as a plausible
          contributor to the deviation above — never a percentage of the deviation itself.
        </p>
      </div>

      <div className="sm:col-span-2 flex flex-col gap-3 border-t border-zinc-100 pt-4 dark:border-zinc-800">
        <div className="grid gap-4 sm:grid-cols-2">
          <EvidenceList title="Supporting evidence" items={attribution.supporting_evidence} />
          <EvidenceList title="Contradicting evidence" items={attribution.contradicting_evidence} />
          <EvidenceList title="Limiting factors" items={attribution.limiting_factors} />
          <EvidenceList
            title="Alternative explanations"
            items={attribution.alternative_explanations}
          />
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
          <span>Data trust:</span>
          <StatusPill tone={qualityTone(attribution.data_quality_state)}>
            {qualityLabel(attribution.data_quality_state)}
          </StatusPill>
        </div>
      </div>
    </div>
  );
}
