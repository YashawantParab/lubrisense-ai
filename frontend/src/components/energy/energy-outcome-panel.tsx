import {
  AttributionLevelBadge,
  ComparabilityStatusBadge,
  EnergyOutcomeStatusBadge,
} from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";
import { associationWording } from "@/lib/energy-outcome-wording";
import { formatKw, formatPct } from "@/lib/energy-format";
import type { EnergyOutcomeVerification } from "@/lib/api/energy-types";

/**
 * A completed maintenance intervention's energy outcome (task §10, a BE-201-shaped case
 * when qualified) — pre/post residual comparison, comparability, and the claim-hierarchy-
 * correct association wording (`associationWording`). Renders exactly the same structure
 * for every `energy_outcome_status` (qualified, probable, no-material-change, inconclusive,
 * deteriorated, insufficient-data) — completion is never implied as automatic success, and
 * a non-qualified outcome is shown just as plainly as a qualified one, never hidden.
 */
export function EnergyOutcomePanel({ outcome }: { outcome: EnergyOutcomeVerification }) {
  const isQualified =
    outcome.energy_outcome_status === "QUALIFIED_RECOVERY" ||
    outcome.energy_outcome_status === "PROBABLE_RECOVERY";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <EnergyOutcomeStatusBadge value={outcome.energy_outcome_status} />
        <ComparabilityStatusBadge value={outcome.comparability_status} />
        <span className="text-xs text-zinc-400 dark:text-zinc-600">
          Intervention <RelativeTime iso={outcome.intervention_timestamp} />
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Pre-intervention residual</dt>
          <dd className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {formatKw(outcome.pre_mean_residual_kw)} ({formatPct(outcome.pre_mean_residual_pct)})
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Post-intervention residual</dt>
          <dd className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {formatKw(outcome.post_mean_residual_kw)} ({formatPct(outcome.post_mean_residual_pct)})
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Residual change</dt>
          <dd className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {formatKw(outcome.residual_change_kw)} ({formatPct(outcome.residual_change_pct)})
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Pre-intervention attribution</dt>
          <dd className="mt-0.5">
            {outcome.pre_attribution_level ? (
              <AttributionLevelBadge value={outcome.pre_attribution_level} />
            ) : (
              <span className="text-sm text-zinc-500 dark:text-zinc-400">Not recorded</span>
            )}
          </dd>
        </div>
      </dl>

      {isQualified && (
        <div className="flex flex-col gap-1.5 rounded-lg bg-emerald-50/60 p-4 dark:bg-emerald-500/[0.06]">
          <p className="text-xs font-semibold tracking-wide text-emerald-700 uppercase dark:text-emerald-400">
            Qualified observed avoided energy
          </p>
          <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {outcome.estimated_avoided_energy_kwh !== null
              ? `~${outcome.estimated_avoided_energy_kwh.toFixed(1)} kWh`
              : "Not estimated"}
          </p>
          <p className="text-sm text-zinc-700 dark:text-zinc-300">{associationWording(outcome)}</p>
          <p className="text-[11px] text-zinc-400 italic dark:text-zinc-600">
            A demonstration-scale, observed figure — never annualized or projected forward.
          </p>
        </div>
      )}

      {!isQualified && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">{associationWording(outcome)}</p>
      )}

      {(outcome.limiting_factors.length > 0 || outcome.alternative_explanations.length > 0) && (
        <div className="grid gap-4 border-t border-zinc-100 pt-3 sm:grid-cols-2 dark:border-zinc-800">
          {outcome.limiting_factors.length > 0 && (
            <div>
              <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Limiting factors
              </p>
              <ul className="mt-1 list-inside list-disc text-sm text-zinc-700 dark:text-zinc-300">
                {outcome.limiting_factors.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {outcome.alternative_explanations.length > 0 && (
            <div>
              <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Alternative explanations
              </p>
              <ul className="mt-1 list-inside list-disc text-sm text-zinc-700 dark:text-zinc-300">
                {outcome.alternative_explanations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
