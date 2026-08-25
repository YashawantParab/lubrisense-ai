import { EnergyAssessmentStatusBadge } from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";
import { formatKw, formatPct } from "@/lib/energy-format";
import { humanize, qualityLabel, qualityTone } from "@/lib/terminology";
import { StatusPill } from "@/components/status-pill";
import type { EnergyAssessment } from "@/lib/api/energy-types";

/** The exact required phrasing (task §6): a comparison against contextual expectation,
 * never a lubrication claim — "Power demand is 13.7% above contextual expectation," not
 * "energy loss due to lubrication." Only rendered when there's a real residual to state. */
function residualSentence(assessment: EnergyAssessment): string | null {
  if (assessment.residual_pct === null) return null;
  const pct = Math.abs(assessment.residual_pct).toFixed(1);
  if (assessment.residual_pct > 0) {
    return `Power demand is ${pct}% above contextual expectation.`;
  }
  if (assessment.residual_pct < 0) {
    return `Power demand is ${pct}% below contextual expectation.`;
  }
  return "Power demand matches contextual expectation.";
}

/**
 * Current `EnergyAssessment` state (task §6) — an observed deviation from contextual
 * expectation, never a lubrication diagnosis. Every field here is a real backend value;
 * this component performs no computation of its own beyond the one required sentence
 * above, which is itself derived directly from `residual_pct`.
 */
export function MachineEnergyCurrent({ assessment }: { assessment: EnergyAssessment }) {
  const sentence = residualSentence(assessment);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <EnergyAssessmentStatusBadge value={assessment.status} />
          {sentence && (
            <span className="text-base font-medium text-zinc-900 dark:text-zinc-100">
              {sentence}
            </span>
          )}
        </div>
        <span className="text-xs text-zinc-400 dark:text-zinc-600">
          As of <RelativeTime iso={assessment.as_of_timestamp} />
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Actual power</dt>
          <dd className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {formatKw(assessment.actual_power_kw)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Expected (contextual)</dt>
          <dd className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {formatKw(assessment.expected_power_kw)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Expected range</dt>
          <dd className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {assessment.expected_lower_kw !== null && assessment.expected_upper_kw !== null
              ? `${assessment.expected_lower_kw.toFixed(2)}–${assessment.expected_upper_kw.toFixed(2)} kW`
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Residual</dt>
          <dd className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {formatKw(assessment.residual_kw)}
            {assessment.residual_pct !== null && ` (${formatPct(assessment.residual_pct)})`}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Data quality</dt>
          <dd className="mt-0.5">
            <StatusPill tone={qualityTone(assessment.data_quality_state)}>
              {qualityLabel(assessment.data_quality_state)}
            </StatusPill>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Baseline / context source</dt>
          <dd className="text-sm text-zinc-700 dark:text-zinc-300">
            {humanize(assessment.baseline_source)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Operating state</dt>
          <dd className="text-sm text-zinc-700 dark:text-zinc-300">
            {assessment.operating_state ? humanize(assessment.operating_state) : "—"}
          </dd>
        </div>
      </dl>
    </div>
  );
}
