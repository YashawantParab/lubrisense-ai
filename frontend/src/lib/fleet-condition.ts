import type { ConditionAssessmentResponse } from "@/lib/api/intelligence-types";
import type { Tone } from "@/lib/terminology";

/**
 * Partitions a machine's latest condition into exactly one fleet-health bucket — used by
 * the Overview's fleet status line/distribution and (implicitly) the Fleet page. Order
 * matters: insufficient-evidence and data-quality limitations are checked before
 * "healthy"/"attention" so a machine never gets miscounted as confidently healthy just
 * because its condition_type happens to read NORMAL_OPERATION-adjacent.
 */
export type FleetBucket =
  "insufficient_evidence" | "data_quality" | "recovering" | "healthy" | "attention";

export const FLEET_BUCKET_LABELS: Record<FleetBucket, string> = {
  healthy: "Healthy / stable",
  attention: "Needs attention",
  recovering: "Recovering",
  data_quality: "Data-quality constrained",
  insufficient_evidence: "Insufficient evidence",
};

export function fleetBucket(
  condition: Pick<ConditionAssessmentResponse, "condition_type" | "lifecycle_state">,
): FleetBucket {
  if (condition.condition_type === "INSUFFICIENT_EVIDENCE") return "insufficient_evidence";
  if (condition.condition_type === "SENSOR_OR_DATA_QUALITY_LIMITATION") return "data_quality";
  if (condition.condition_type === "NORMAL_OPERATION") return "healthy";
  if (condition.lifecycle_state === "IMPROVING") return "recovering";
  return "attention";
}

export const FLEET_BUCKET_TONE: Record<FleetBucket, Tone> = {
  healthy: "ok",
  attention: "warn",
  recovering: "info",
  data_quality: "neutral",
  insufficient_evidence: "neutral",
};

const SEVERITY_RANK: Record<string, number> = { CRITICAL: 3, HIGH: 2, WARNING: 1, INFO: 0 };

export function severityRank(value: string): number {
  return SEVERITY_RANK[value] ?? -1;
}
