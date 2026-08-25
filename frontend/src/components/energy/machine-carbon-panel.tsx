import Link from "next/link";

import {
  CarbonEstimateStatusBadge,
  ComparabilityStatusBadge,
  ComparisonConfidenceBadge,
} from "@/components/badges";
import type { CarbonImpactEstimate, EnergyOutcomeVerification } from "@/lib/api/energy-types";
import { calculationLine, extractFactorProvenance, formatEffectivePeriod } from "@/lib/carbon-calc";

const NO_FACTOR_STATUSES = new Set(["FACTOR_NOT_CONFIGURED", "FACTOR_NOT_APPLICABLE"]);

/**
 * Machine-level carbon estimate (task §11, extended Enterprise Product Rebuild Pass 2
 * §6/§7 with a "How this is calculated" disclosure). Strictly downstream of a qualified
 * energy outcome. When no emission factor is configured/applicable, this explicitly says
 * so rather than rendering "0 kg" (task §20's "never a real zero" rule applies here
 * exactly as it does at the portfolio level). No "carbon saved"/"certified reduction"/
 * net-zero language anywhere in this component.
 */
export function MachineCarbonPanel({
  estimate,
  outcome,
}: {
  estimate: CarbonImpactEstimate;
  /** The qualifying `EnergyOutcomeVerification` this estimate is downstream of — when
   * passed, enables the comparison-quality + energy-outcome-provenance trace in "How
   * this is calculated" (Pass 2 §7's carbon-traceability requirement). Optional since not
   * every caller has it loaded. */
  outcome?: EnergyOutcomeVerification;
}) {
  const missingFactor = NO_FACTOR_STATUSES.has(estimate.estimate_status);
  const factor = extractFactorProvenance(estimate.provenance);
  const calculation = calculationLine(
    estimate.qualified_avoided_energy_kwh,
    estimate.emission_factor_value,
    estimate.emission_factor_unit,
  );

  return (
    <div className="flex flex-col gap-3 rounded-lg bg-zinc-50/70 p-4 dark:bg-zinc-900/40">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
          Carbon
        </p>
        <CarbonEstimateStatusBadge value={estimate.estimate_status} />
      </div>

      {missingFactor ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Emission factor not{" "}
          {estimate.estimate_status === "FACTOR_NOT_CONFIGURED" ? "configured" : "applicable"} for
          this site/period — no CO2e figure can be computed, and this is not the same as zero
          impact.
        </p>
      ) : estimate.estimated_co2e_kg !== null ? (
        <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          {estimate.estimated_co2e_kg.toFixed(2)} kg CO2e
        </p>
      ) : (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          No estimate is available for this outcome.
        </p>
      )}

      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-zinc-500 dark:text-zinc-400">Qualified avoided energy</dt>
          <dd className="text-zinc-800 dark:text-zinc-200">
            {estimate.qualified_avoided_energy_kwh !== null
              ? `${estimate.qualified_avoided_energy_kwh.toFixed(1)} kWh`
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-zinc-500 dark:text-zinc-400">Emission factor</dt>
          <dd className="text-zinc-800 dark:text-zinc-200">
            {estimate.emission_factor_value !== null
              ? `${estimate.emission_factor_value} ${estimate.emission_factor_unit ?? ""}`
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-zinc-500 dark:text-zinc-400">Method</dt>
          <dd className="text-zinc-800 dark:text-zinc-200">{estimate.method ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-zinc-500 dark:text-zinc-400">Observed period</dt>
          <dd className="text-zinc-800 dark:text-zinc-200">
            {estimate.observed_period_start && estimate.observed_period_end
              ? `${new Date(estimate.observed_period_start).toLocaleDateString()}–${new Date(estimate.observed_period_end).toLocaleDateString()}`
              : "—"}
          </dd>
        </div>
      </dl>

      {estimate.limitations.length > 0 && (
        <ul className="border-t border-zinc-200 pt-2 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          {estimate.limitations.map((item) => (
            <li key={item}>— {item}</li>
          ))}
        </ul>
      )}

      <details className="border-t border-zinc-200 pt-2 dark:border-zinc-800">
        <summary className="cursor-pointer text-xs font-medium text-sky-600 select-none dark:text-sky-400">
          How this is calculated
        </summary>
        <div className="mt-2 flex flex-col gap-3 text-xs text-zinc-600 dark:text-zinc-400">
          <p className="font-mono text-zinc-800 dark:text-zinc-200">
            Estimated CO2e = Qualified observed avoided energy × Applicable configured electricity
            emission factor
          </p>
          {calculation && (
            <p className="font-mono text-zinc-800 dark:text-zinc-200">{calculation}</p>
          )}

          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div>
              <dt className="text-zinc-500 dark:text-zinc-400">Factor source</dt>
              <dd className="text-zinc-800 dark:text-zinc-200">
                {factor.sourceName ?? "Not available"}
                {factor.sourceReference ? ` (${factor.sourceReference})` : ""}
              </dd>
            </div>
            <div>
              <dt className="text-zinc-500 dark:text-zinc-400">Factor effective period</dt>
              <dd className="text-zinc-800 dark:text-zinc-200">{formatEffectivePeriod(factor)}</dd>
            </div>
            <div>
              <dt className="text-zinc-500 dark:text-zinc-400">Factor provenance</dt>
              <dd className="text-zinc-800 dark:text-zinc-200">
                {factor.provenanceLabel
                  ? factor.provenanceLabel.replace(/_/g, " ")
                  : "Not available"}
              </dd>
            </div>
            {outcome && (
              <>
                <div>
                  <dt className="text-zinc-500 dark:text-zinc-400">Comparability</dt>
                  <dd className="mt-0.5">
                    <ComparabilityStatusBadge value={outcome.comparability_status} />
                  </dd>
                </div>
                <div>
                  <dt className="text-zinc-500 dark:text-zinc-400">Comparison confidence</dt>
                  <dd className="mt-0.5">
                    <ComparisonConfidenceBadge value={outcome.comparison_confidence} />
                  </dd>
                </div>
                <div>
                  <dt className="text-zinc-500 dark:text-zinc-400">Source maintenance case</dt>
                  <dd className="text-zinc-800 dark:text-zinc-200">
                    <Link
                      href={`/maintenance/${outcome.maintenance_case_id}`}
                      className="text-sky-600 hover:underline dark:text-sky-400"
                    >
                      View qualified energy outcome →
                    </Link>
                  </dd>
                </div>
              </>
            )}
          </dl>

          <ul className="list-disc space-y-1 pl-4">
            <li>
              The energy outcome had to qualify first — a completed maintenance intervention with a
              comparable pre/post measurement window and a residual improvement.
            </li>
            <li>
              An emission factor must be configured and applicable to this site and period, or no
              CO2e figure can be computed.
            </li>
            <li>This is an operational estimate, not a certified carbon-accounting figure.</li>
            <li>Derived from synthetic demonstration data — not a real facility measurement.</li>
            <li>Not audited corporate carbon accounting.</li>
          </ul>
        </div>
      </details>

      <p className="text-[11px] text-zinc-400 italic dark:text-zinc-600">
        Operational estimate derived from qualified observed energy recovery and a configured
        electricity emission factor. Never a claim of certified reduction or net-zero contribution.
      </p>
    </div>
  );
}
