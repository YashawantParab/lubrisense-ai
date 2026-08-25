/**
 * Display order + bar color for the fixed categorical distributions the Portfolio
 * Intelligence API returns (backend/app/domain/enums.py — ActionReadinessState,
 * PortfolioPriority, EnergyPortfolioBucket, MaintenanceOutcomeBucket, DataTrustCategory).
 * Order is "healthy/resolved first, most-limiting last" — the same convention
 * `fleet-condition.ts`'s `FLEET_BUCKET` order already established. Never reorders by
 * count — a stable category order is what makes a distribution bar scannable across
 * sites/areas/reloads.
 */

export const PRIORITY_ORDER = [
  "MONITOR",
  "ATTENTION",
  "HIGH_ATTENTION",
  "CRITICAL_ATTENTION",
  "DATA_LIMITED",
] as const;

export const PRIORITY_BAR_CLASS: Record<string, string> = {
  MONITOR: "bg-emerald-500",
  ATTENTION: "bg-amber-400",
  HIGH_ATTENTION: "bg-amber-500",
  CRITICAL_ATTENTION: "bg-red-500",
  DATA_LIMITED: "bg-zinc-300 dark:bg-zinc-600",
};

export const ACTION_READINESS_ORDER = [
  "MONITORING_ONLY",
  "HUMAN_ACTION_REQUIRED",
  "ASSESSMENT_BLOCKED",
  "DATA_LIMITED",
  "NOT_YET_ASSESSED",
] as const;

export const ACTION_READINESS_BAR_CLASS: Record<string, string> = {
  MONITORING_ONLY: "bg-emerald-500",
  HUMAN_ACTION_REQUIRED: "bg-amber-500",
  ASSESSMENT_BLOCKED: "bg-red-500",
  DATA_LIMITED: "bg-zinc-300 dark:bg-zinc-600",
  NOT_YET_ASSESSED: "bg-zinc-300 dark:bg-zinc-600",
};

export const ENERGY_BUCKET_ORDER = [
  "NORMAL_ENERGY_BEHAVIOR",
  "ACTIVE_ELEVATED_ENERGY",
  "ATTRIBUTION_SUPPORTED_OPPORTUNITY",
  "OUTCOME_AWAITING_VERIFICATION",
  "QUALIFIED_ENERGY_RECOVERY",
  "INCONCLUSIVE_OUTCOME",
  "OUTCOME_DETERIORATED",
  "INSUFFICIENT_ENERGY_DATA",
] as const;

export const ENERGY_BUCKET_BAR_CLASS: Record<string, string> = {
  NORMAL_ENERGY_BEHAVIOR: "bg-emerald-500",
  ACTIVE_ELEVATED_ENERGY: "bg-amber-400",
  ATTRIBUTION_SUPPORTED_OPPORTUNITY: "bg-amber-500",
  OUTCOME_AWAITING_VERIFICATION: "bg-sky-500",
  QUALIFIED_ENERGY_RECOVERY: "bg-emerald-600",
  INCONCLUSIVE_OUTCOME: "bg-zinc-300 dark:bg-zinc-600",
  OUTCOME_DETERIORATED: "bg-red-500",
  INSUFFICIENT_ENERGY_DATA: "bg-zinc-200 dark:bg-zinc-700",
};

export const MAINTENANCE_OUTCOME_ORDER = [
  "OPEN_ACTION",
  "COMPLETED_OUTCOME_NOT_ASSESSED",
  "COMPLETED_QUALIFIED_RECOVERY",
  "COMPLETED_PROBABLE_RECOVERY",
  "COMPLETED_NO_MATERIAL_CHANGE",
  "COMPLETED_INCONCLUSIVE",
  "COMPLETED_DETERIORATED",
] as const;

export const MAINTENANCE_OUTCOME_BAR_CLASS: Record<string, string> = {
  OPEN_ACTION: "bg-amber-500",
  COMPLETED_OUTCOME_NOT_ASSESSED: "bg-sky-500",
  COMPLETED_QUALIFIED_RECOVERY: "bg-emerald-600",
  COMPLETED_PROBABLE_RECOVERY: "bg-emerald-400",
  COMPLETED_NO_MATERIAL_CHANGE: "bg-zinc-300 dark:bg-zinc-600",
  COMPLETED_INCONCLUSIVE: "bg-zinc-300 dark:bg-zinc-600",
  COMPLETED_DETERIORATED: "bg-red-500",
};

export const DATA_TRUST_ORDER = [
  "DECISION_EVIDENCE_TRUSTED",
  "CONFIDENCE_REDUCED",
  "ASSESSMENT_BLOCKED",
  "ACTION_BLOCKED",
] as const;

export const DATA_TRUST_BAR_CLASS: Record<string, string> = {
  DECISION_EVIDENCE_TRUSTED: "bg-emerald-500",
  CONFIDENCE_REDUCED: "bg-amber-500",
  ASSESSMENT_BLOCKED: "bg-red-500",
  ACTION_BLOCKED: "bg-red-600",
};

/** Ranks sites by real backend-reported counts — critical attention first, then
 * attention, never a fabricated composite score (design doc §"risk/priority model").
 * `SitePerformance` doesn't carry a priority field of its own (only per-asset priority
 * does), so this is the most defensible presentation-layer ordering available. */
export function bySeverityThenAttention<
  T extends { critical_attention_count: number; attention_count: number },
>(sites: T[]): T[] {
  return [...sites].sort(
    (a, b) =>
      b.critical_attention_count - a.critical_attention_count ||
      b.attention_count - a.attention_count,
  );
}

/** Condition types are an open, dynamic vocabulary (unlike the five fixed enums above) —
 * site/area responses expose a raw `condition_distribution` map rather than a fixed
 * bucket set. This cycles a small, purely-decorative color palette (never load-bearing —
 * every legend row repeats the count/label as text) sorted by count descending, so the
 * most common condition reads first regardless of which condition types are present. */
const DYNAMIC_PALETTE = [
  "bg-sky-500",
  "bg-violet-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-teal-500",
  "bg-indigo-500",
  "bg-fuchsia-500",
  "bg-lime-500",
] as const;

export function toDynamicSegments(
  distribution: Record<string, number>,
  labelFor: (value: string) => string,
): { key: string; label: string; count: number; colorClass: string }[] {
  return Object.entries(distribution)
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([key, count], index) => ({
      key,
      label: labelFor(key),
      count,
      colorClass: DYNAMIC_PALETTE[index % DYNAMIC_PALETTE.length],
    }));
}

/** Sorts a fixed category set into display order, dropping zero counts — shared shape
 * every `SegmentedDistributionBar` caller passes in. */
export function toSegments(
  distribution: Record<string, number>,
  order: readonly string[],
  barClass: Record<string, string>,
  labelFor: (value: string) => string,
): { key: string; label: string; count: number; colorClass: string }[] {
  return order
    .map((key) => ({
      key,
      label: labelFor(key),
      count: distribution[key] ?? 0,
      colorClass: barClass[key] ?? "bg-zinc-300 dark:bg-zinc-600",
    }))
    .filter((segment) => segment.count > 0);
}
