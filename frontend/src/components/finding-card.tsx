import { SeverityBadge } from "@/components/badges";
import type { RuleFindingResponse } from "@/lib/api/rules-types";

/**
 * Human headline for each rule-finding type — deliberately hand-written product language,
 * not a mechanical underscore-to-space replacement of the internal rule-finding type.
 * `finding.message` (built by the rule itself) already reads as a full sentence with the
 * observed/baseline numbers folded in, so it carries the supporting detail; this headline
 * is just the "what kind of thing is this" label above it.
 */
export const FINDING_TYPE_LABELS: Record<string, string> = {
  FLOW_BELOW_CONTEXTUAL_BASELINE: "Lubricant flow below expected level",
  PRESSURE_ABOVE_CONTEXTUAL_BASELINE: "Line pressure above expected level",
  PRESSURE_BUILD_SLOW: "Pressure building slower than expected",
  PUMP_CURRENT_ABOVE_BASELINE: "Pump drawing more current than expected",
  PUMP_RUNTIME_ABOVE_BASELINE: "Pump running longer than expected",
  CYCLE_DURATION_ABOVE_BASELINE: "Lubrication cycle taking longer than expected",
  CYCLE_COMPLETION_FAILURE: "Lubrication cycle failed to complete",
  RESERVOIR_LEVEL_LOW: "Reservoir level low",
  RESERVOIR_DEPLETION_ABNORMAL: "Reservoir depleting faster than expected",
  BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE: "Bearing temperature above expected level",
  VIBRATION_ABOVE_CONTEXTUAL_BASELINE: "Vibration above expected level",
  FLOW_PRESSURE_RESTRICTION_PATTERN: "Flow and pressure pattern consistent with a restriction",
  FLOW_PRESSURE_LEAKAGE_PATTERN: "Flow and pressure pattern consistent with a leak",
  PUMP_DEGRADATION_PATTERN: "Pattern consistent with pump degradation",
  LUBRICATION_PATH_DEGRADATION_PATTERN: "Pattern consistent with lubrication-path degradation",
  INDEPENDENT_BEARING_CONDITION_PATTERN: "Independent bearing-condition pattern detected",
  INSUFFICIENT_TRUSTED_DATA: "Insufficient trusted sensor data",
};

export function findingHeadline(findingType: string): string {
  return (
    FINDING_TYPE_LABELS[findingType] ??
    findingType
      .toLowerCase()
      .split("_")
      .map((w) => w[0]?.toUpperCase() + w.slice(1))
      .join(" ")
  );
}

export function FindingCard({ finding }: { finding: RuleFindingResponse }) {
  return (
    <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {findingHeadline(finding.finding_type)}
        </span>
        <SeverityBadge value={finding.severity} />
      </div>
      <p className="mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">{finding.message}</p>
      {finding.limitations.length > 0 && (
        <p className="mt-1.5 text-xs text-zinc-400 dark:text-zinc-600">{finding.limitations[0]}</p>
      )}
      <details className="mt-2">
        <summary className="cursor-pointer text-xs font-medium text-sky-600 select-none dark:text-sky-400">
          Technical detail
        </summary>
        <dl className="mt-1.5 grid grid-cols-2 gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
          <div>
            <dt>Rule finding type</dt>
            <dd className="font-mono text-zinc-800 dark:text-zinc-200">{finding.finding_type}</dd>
          </div>
          <div>
            <dt>State</dt>
            <dd className="text-zinc-800 dark:text-zinc-200">{finding.state}</dd>
          </div>
          <div>
            <dt>Evidence strength</dt>
            <dd className="text-zinc-800 dark:text-zinc-200">{finding.evidence_strength}</dd>
          </div>
          <div>
            <dt>Rule</dt>
            <dd className="font-mono text-zinc-800 dark:text-zinc-200">
              {finding.rule_id} (v{finding.rule_version})
            </dd>
          </div>
        </dl>
      </details>
    </div>
  );
}
