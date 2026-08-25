import Link from "next/link";

import { SectionCard } from "@/components/section-card";
import { SegmentedDistributionBar } from "@/components/segmented-distribution-bar";
import { humanize } from "@/lib/terminology";
import { ENERGY_BUCKET_BAR_CLASS, ENERGY_BUCKET_ORDER, toSegments } from "@/lib/portfolio";

export interface EnergyEfficiencyPanelProps {
  /** Full bucket distribution — only the organization-level response exposes this;
   * site/area responses expose just the summary counts below. */
  distribution?: Record<string, number>;
  activeOpportunities: number;
  attributionSupportedOpportunities?: number;
  qualifiedRecoveryCount: number;
  qualifiedAvoidedEnergyKwhTotal: number;
}

/**
 * CLAUDE.md's energy-portfolio semantics, made visually explicit: "active opportunities"
 * (elevated energy demand, possibly lubrication-attribution-supported — never yet a
 * benefit claim) and "qualified outcomes" (an actual completed, comparability-gated,
 * residual-verified recovery) are two different headings, never combined under
 * "Savings." Numbers come straight from the backend's own EnergySection/flattened
 * site-energy fields — this component performs no aggregation of its own.
 */
export function EnergyEfficiencyPanel({
  distribution,
  activeOpportunities,
  attributionSupportedOpportunities,
  qualifiedRecoveryCount,
  qualifiedAvoidedEnergyKwhTotal,
}: EnergyEfficiencyPanelProps) {
  return (
    <SectionCard title="Energy & efficiency">
      <div className="grid gap-6 sm:grid-cols-2">
        <div className="flex flex-col gap-2 rounded-lg bg-amber-50/60 p-4 dark:bg-amber-500/[0.06]">
          <p className="text-xs font-semibold tracking-wide text-amber-700 uppercase dark:text-amber-400">
            Active opportunities
          </p>
          <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {activeOpportunities}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Assets currently showing elevated contextual energy demand.
            {attributionSupportedOpportunities !== undefined &&
            attributionSupportedOpportunities > 0
              ? ` ${attributionSupportedOpportunities} of these also have lubrication-attribution evidence supporting the deviation.`
              : ""}
          </p>
          <p className="text-[11px] text-zinc-400 italic dark:text-zinc-600">
            Not yet a verified outcome — no maintenance intervention has been completed and compared
            for these assets.
          </p>
        </div>

        <div className="flex flex-col gap-2 rounded-lg bg-emerald-50/60 p-4 dark:bg-emerald-500/[0.06]">
          <p className="text-xs font-semibold tracking-wide text-emerald-700 uppercase dark:text-emerald-400">
            Qualified outcomes
          </p>
          <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {qualifiedRecoveryCount}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {qualifiedRecoveryCount === 0
              ? "No comparability-gated, residual-verified energy recovery has been qualified yet."
              : `Qualified observed avoided energy: ~${qualifiedAvoidedEnergyKwhTotal.toFixed(1)} kWh, from a completed maintenance intervention with a comparable pre/post measurement window.`}
          </p>
          <p className="text-[11px] text-zinc-400 italic dark:text-zinc-600">
            A demonstration-scale, observed outcome — never annualized or projected forward.
          </p>
        </div>
      </div>

      {distribution && (
        <div className="mt-6">
          <p className="mb-2 text-xs font-medium text-zinc-400 dark:text-zinc-500">
            All monitored assets by energy status
          </p>
          <SegmentedDistributionBar
            segments={toSegments(
              distribution,
              ENERGY_BUCKET_ORDER,
              ENERGY_BUCKET_BAR_CLASS,
              humanize,
            )}
            emptyLabel="No energy assessments recorded yet."
          />
        </div>
      )}

      <Link
        href="/data-quality"
        className="mt-4 inline-block text-xs text-sky-600 hover:underline dark:text-sky-400"
      >
        Energy assessments depend on data quality — see Data Quality →
      </Link>
    </SectionCard>
  );
}
