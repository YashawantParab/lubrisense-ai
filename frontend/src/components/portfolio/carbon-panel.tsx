import Link from "next/link";

import { SectionCard } from "@/components/section-card";

export interface CarbonPanelProps {
  estimatedCo2eKgTotal: number;
  /** Count of outcomes that actually produced a carbon estimate — only the
   * organization/site responses expose this; area does not. When omitted, this panel
   * still avoids implying a false zero (see below). */
  qualifyingOutcomeCount?: number;
  missingFactorCount?: number;
}

/**
 * Carbon appears strictly downstream of a qualified energy outcome (CLAUDE.md's energy/
 * carbon boundary) — deliberately a small, secondary panel, never the visual centerpiece.
 * Zero is never rendered as "0 kg CO2e" when it actually means "no qualified outcome has
 * an estimate yet" (task §20/§10) — those two states are visually and textually distinct.
 */
export function CarbonPanel({
  estimatedCo2eKgTotal,
  qualifyingOutcomeCount,
  missingFactorCount,
}: CarbonPanelProps) {
  const hasEstimate =
    qualifyingOutcomeCount !== undefined ? qualifyingOutcomeCount > 0 : estimatedCo2eKgTotal > 0;

  return (
    <SectionCard title="Carbon">
      {hasEstimate ? (
        <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
          <div>
            <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
              {estimatedCo2eKgTotal.toFixed(2)} kg CO2e
            </p>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Estimated energy-related CO2e impact from qualified observed outcomes
              {qualifyingOutcomeCount !== undefined
                ? ` (${qualifyingOutcomeCount} qualifying outcome${qualifyingOutcomeCount === 1 ? "" : "s"})`
                : ""}
              .
            </p>
          </div>
          {missingFactorCount !== undefined && missingFactorCount > 0 && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {missingFactorCount} qualified outcome{missingFactorCount === 1 ? "" : "s"} missing an
              applicable emission factor
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No qualified energy outcome currently has a carbon estimate — this is not a zero impact,
          it means no eligible outcome + configured emission factor pair exists yet.
        </p>
      )}
      <p className="mt-3 text-[11px] text-zinc-400 italic dark:text-zinc-600">
        Operational estimate derived from qualified observed energy recovery and configured
        electricity emission factor. Never a claim of &ldquo;carbon saved&rdquo; or a sustainability
        commitment.
      </p>

      <details className="mt-2 border-t border-zinc-100 pt-2 dark:border-zinc-800">
        <summary className="cursor-pointer text-xs font-medium text-sky-600 select-none dark:text-sky-400">
          How this is calculated
        </summary>
        <div className="mt-2 flex flex-col gap-2 text-xs text-zinc-600 dark:text-zinc-400">
          <p className="font-mono text-zinc-800 dark:text-zinc-200">
            Estimated CO2e = Qualified observed avoided energy × Applicable configured electricity
            emission factor
          </p>
          <ul className="list-disc space-y-1 pl-4">
            <li>
              Only a completed maintenance intervention with a comparable pre/post measurement
              window and a qualified residual improvement contributes to this total.
            </li>
            <li>
              A site&rsquo;s emission factor must be configured and applicable to the
              outcome&rsquo;s period, or that outcome contributes nothing to this total (see
              &ldquo;missing an applicable emission factor&rdquo; above).
            </li>
            <li>An operational estimate, not certified or audited carbon accounting.</li>
            <li>Derived from synthetic demonstration data across this fleet.</li>
          </ul>
          <Link
            href="/energy?status=qualified"
            className="text-sky-600 hover:underline dark:text-sky-400"
          >
            See each qualifying outcome&rsquo;s own calculation →
          </Link>
        </div>
      </details>
    </SectionCard>
  );
}
