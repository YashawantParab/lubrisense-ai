import { CarbonEstimateStatusBadge } from "@/components/badges";
import type { CarbonImpactEstimate } from "@/lib/api/energy-types";

const NO_FACTOR_STATUSES = new Set(["FACTOR_NOT_CONFIGURED", "FACTOR_NOT_APPLICABLE"]);

/**
 * Machine-level carbon estimate (task §11) — strictly downstream of a qualified energy
 * outcome. When no emission factor is configured/applicable, this explicitly says so
 * rather than rendering "0 kg" (task §20's "never a real zero" rule applies here exactly
 * as it does at the portfolio level). No "carbon saved"/"certified reduction"/net-zero
 * language anywhere in this component.
 */
export function MachineCarbonPanel({ estimate }: { estimate: CarbonImpactEstimate }) {
  const missingFactor = NO_FACTOR_STATUSES.has(estimate.estimate_status);

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

      <p className="text-[11px] text-zinc-400 italic dark:text-zinc-600">
        Operational estimate derived from qualified observed energy recovery and a configured
        electricity emission factor. Never a claim of certified reduction or net-zero contribution.
      </p>
    </div>
  );
}
