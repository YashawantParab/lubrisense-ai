/**
 * Human-readable baseline naming (Enterprise Product Rebuild §12) — the raw
 * `context_key`/`strategy` enum pair (e.g. `"operating_state=STOPPED"` /
 * `CONTEXTUAL_ASSET_BASELINE`) is an implementation detail, not something an engineer can
 * scan a table of. This derives a plain-language name from the same fields without
 * changing any technical ID — `context_key`/`strategy`/`id`/`version` remain available
 * verbatim under each row's own technical detail.
 */

import type { BaselineProfileResponse } from "@/lib/api/baselines-types";
import { humanize } from "@/lib/terminology";

const MEASUREMENT_LABEL: Record<string, string> = {
  BEARING_TEMPERATURE: "Bearing temperature",
  VIBRATION_RMS: "Vibration (RMS)",
  VIBRATION_PEAK: "Vibration (peak)",
  MACHINE_POWER: "Machine power",
  RESERVOIR_LEVEL: "Reservoir level",
  PRESSURE: "Lubrication pressure",
  PUMP_CURRENT: "Pump current",
  RPM: "Rotational speed",
  LOAD: "Load",
  LUBRICANT_FLOW: "Lubricant flow",
  LUBRICANT_TEMPERATURE: "Lubricant temperature",
};

export function measurementLabel(measurementType: string): string {
  return MEASUREMENT_LABEL[measurementType] ?? humanize(measurementType);
}

function operatingContextLabel(profile: BaselineProfileResponse): string {
  const operatingState = profile.context?.operating_state;
  if (typeof operatingState === "string" && operatingState) {
    return `${humanize(operatingState).toLowerCase()} operation`;
  }
  if (profile.strategy === "STATIC_ENGINEERING_REFERENCE") return "engineering reference range";
  if (profile.strategy === "ROLLING_ASSET_BASELINE") return "recent history, any operating state";
  return "any operating state";
}

/** e.g. "Bearing temperature — stopped operation" / "Machine power — loaded operation". */
export function humanizedBaselineName(profile: BaselineProfileResponse): string {
  return `${measurementLabel(profile.measurement_type)} — ${operatingContextLabel(profile)}`;
}

/** A plain-language description of what population this baseline is drawn from. */
export function baselineContextDescription(profile: BaselineProfileResponse): string {
  return operatingContextLabel(profile);
}

/** The statistically expected range for this baseline, from its persisted statistics —
 * never fabricated when statistics are absent (e.g. a not-yet-built profile). */
export function expectedRangeLabel(
  statistics: Record<string, number> | null,
  unit: string | null,
): string {
  if (!statistics) return "Not yet available";
  const low = statistics.p05 ?? statistics.min;
  const high = statistics.p95 ?? statistics.max;
  if (low === undefined || high === undefined) return "Not yet available";
  const suffix = unit ? ` ${unit}` : "";
  return `${low.toFixed(1)}${suffix} – ${high.toFixed(1)}${suffix}`;
}
