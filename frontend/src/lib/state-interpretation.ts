import type { Tone } from "@/lib/terminology";

/**
 * Turns a normalized state-estimate reading (0=normal..1=severely degraded, trend,
 * uncertainty) into the plain-language interpretation a non-engineer needs — the
 * normalized index itself is real, persisted evidence and stays visible as supporting
 * detail, but it is never the first thing shown. Mirrors the same threshold
 * (`minimum_meaningful_level`, backend `condition_intelligence_v1.yaml`) the backend
 * itself uses to decide whether a level counts as meaningfully elevated, so this never
 * disagrees with what the real condition assessment concluded.
 */
const MINIMUM_MEANINGFUL_LEVEL = 0.15;

export interface StateInterpretation {
  headline: string;
  tone: Tone;
}

export function interpretState(
  trend: string,
  stateValue: number,
  options: { unavailable?: boolean } = {},
): StateInterpretation {
  if (options.unavailable) {
    return { headline: "Not enough recent data", tone: "neutral" };
  }
  const elevated = Math.abs(stateValue) >= MINIMUM_MEANINGFUL_LEVEL;

  if (trend === "DETERIORATING") {
    return { headline: "Deteriorating", tone: "warn" };
  }
  if (trend === "IMPROVING") {
    return elevated
      ? { headline: "Improving toward normal", tone: "warn" }
      : { headline: "Normal, improving", tone: "ok" };
  }
  // STABLE or UNKNOWN-but-not-flagged-unavailable
  return elevated
    ? { headline: "Elevated, holding steady", tone: "warn" }
    : { headline: "Normal, stable", tone: "ok" };
}

export const STATE_TYPE_LABELS: Record<string, string> = {
  LUBRICATION_DELIVERY_STATE: "Lubrication delivery",
  BEARING_CONDITION_STATE: "Bearing condition",
};
