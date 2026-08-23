/**
 * Shared derivation logic for the Data Quality page — the single place trust category,
 * issue category, recommended action, and decision-impact are computed from real backend
 * fields, so the summary chips, distribution bar, table, and detail view never compute the
 * same fact two different ways (CLAUDE.md §28's "never calculate product-critical truth
 * differently in each frontend component", applied on the frontend side of this
 * codebase's established pattern of composing single-source read models per page — see
 * `lib/action-readiness.ts`, `lib/fleet-condition.ts`).
 */

import { fleetBucket } from "@/lib/fleet-condition";
import type { ReadinessMode } from "@/lib/action-readiness";
import type { ConditionAssessmentResponse } from "@/lib/api/intelligence-types";
import type {
  QualityIssueResponse,
  QualityState,
  SensorQualityRecordResponse,
} from "@/lib/api/data-quality-types";

// --- Trust category (primary filter) -------------------------------------------------

export type TrustFilter = "ALL" | "TRUSTED" | "NEEDS_ATTENTION" | "UNTRUSTED";

export const TRUST_FILTER_LABEL: Record<TrustFilter, string> = {
  ALL: "All",
  TRUSTED: "Trusted",
  NEEDS_ATTENTION: "Needs attention",
  UNTRUSTED: "Untrusted",
};

/** `USABLE_WITH_CAUTION` and `UNUSABLE` are both "needs a person's attention" at the
 * fleet-summary level; `UNTRUSTED` narrows to just `UNUSABLE` for the dedicated filter,
 * matching the product framing in CLAUDE.md's brief (Trusted / Needs attention /
 * Untrusted, not five overlapping severities). */
export function matchesTrustFilter(state: QualityState, filter: TrustFilter): boolean {
  if (filter === "ALL") return true;
  if (filter === "TRUSTED") return state === "TRUSTED";
  if (filter === "UNTRUSTED") return state === "UNUSABLE";
  return state === "USABLE_WITH_CAUTION" || state === "UNUSABLE";
}

export const TRUST_LABEL: Record<QualityState, string> = {
  TRUSTED: "Trusted",
  USABLE_WITH_CAUTION: "Use with caution",
  UNUSABLE: "Not trustworthy",
};

export function trustTone(state: QualityState): "ok" | "warn" | "error" {
  if (state === "TRUSTED") return "ok";
  if (state === "USABLE_WITH_CAUTION") return "warn";
  return "error";
}

// --- Issue category (secondary filter) ------------------------------------------------

export type IssueCategory =
  "STALE" | "DROPOUT" | "DRIFT" | "OUTLIER" | "COMMUNICATION_LOSS" | "OTHER";

export const ISSUE_CATEGORY_LABEL: Record<IssueCategory, string> = {
  STALE: "Stale data",
  DROPOUT: "Signal dropout",
  DRIFT: "Sensor drift",
  OUTLIER: "Outlier / implausible reading",
  COMMUNICATION_LOSS: "Communication loss",
  OTHER: "Other",
};

export const ISSUE_CATEGORY_MEANING: Record<IssueCategory, string> = {
  STALE: "Sensor has not reported within the expected freshness window.",
  DROPOUT: "Expected observations are missing intermittently or continuously.",
  DRIFT: "Signal behavior is inconsistent with expected/reference behavior.",
  OUTLIER: "Measurement is physically or statistically implausible.",
  COMMUNICATION_LOSS: "Data path interrupted or unavailable.",
  OTHER: "A different, less common data-quality dimension.",
};

// Only real `QualityIssueType` values this policy can produce
// (`backend/app/domain/enums.py`) are mapped — never an invented issue type.
const ISSUE_CATEGORY_BY_TYPE: Record<string, IssueCategory> = {
  STALE_STREAM: "STALE",
  MISSING_VALUE: "DROPOUT",
  SEQUENCE_GAP: "DROPOUT",
  LATE_ARRIVAL: "DROPOUT",
  VERY_LATE_ARRIVAL: "DROPOUT",
  SENSOR_DRIFT_SUSPECTED: "DRIFT",
  OUT_OF_RANGE: "OUTLIER",
  INVALID_VALUE: "OUTLIER",
  UNIT_MISMATCH: "OUTLIER",
  SPIKE_DETECTED: "OUTLIER",
  STUCK_SENSOR_SUSPECTED: "OUTLIER",
  COMMUNICATION_LOSS: "COMMUNICATION_LOSS",
};

export function issueCategoryFor(issueType: string): IssueCategory {
  return ISSUE_CATEGORY_BY_TYPE[issueType] ?? "OTHER";
}

/** The dominant active issue for a sensor's compact table row — worst severity first,
 * most recently seen as the tiebreak. A sensor can have more than one active issue
 * (different rules can fire independently); the detail view lists every one of them, this
 * only picks which single issue heads the row. */
const SEVERITY_RANK: Record<string, number> = { CRITICAL: 3, ERROR: 2, WARNING: 1, INFO: 0 };

export function primaryIssueFor(issues: QualityIssueResponse[]): QualityIssueResponse | null {
  if (issues.length === 0) return null;
  return [...issues].sort((a, b) => {
    const rank = (SEVERITY_RANK[b.severity] ?? -1) - (SEVERITY_RANK[a.severity] ?? -1);
    if (rank !== 0) return rank;
    return new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime();
  })[0];
}

// --- Recommended next step --------------------------------------------------------------

// Same generic, non-diagnostic action vocabulary the platform already uses elsewhere
// (inspect/verify) — never a diagnosis of the machine itself.
const RECOMMENDED_ACTION: Partial<Record<string, string>> = {
  STALE_STREAM: "Inspect sensor connectivity",
  MISSING_VALUE: "Inspect sensor wiring/connectivity",
  SEQUENCE_GAP: "Inspect sensor connectivity",
  LATE_ARRIVAL: "Verify gateway/network latency",
  VERY_LATE_ARRIVAL: "Verify gateway/network latency",
  CLOCK_OFFSET_SUSPECTED: "Verify gateway/sensor clock sync",
  CLOCK_DRIFT_SUSPECTED: "Verify gateway/sensor clock sync",
  SENSOR_DRIFT_SUSPECTED: "Inspect sensor calibration/mounting",
  STUCK_SENSOR_SUSPECTED: "Inspect sensor connectivity",
  SPIKE_DETECTED: "Verify sensor mounting/wiring",
  OUT_OF_RANGE: "Verify sensor calibration",
  INVALID_VALUE: "Verify sensor calibration",
  UNIT_MISMATCH: "Verify sensor/gateway unit configuration",
  COMMUNICATION_LOSS: "Inspect gateway/network connectivity",
  OUT_OF_ORDER: "Inspect gateway/network connectivity",
  DUPLICATE_PATTERN: "Inspect gateway/network connectivity",
  CONTEXT_INCONSISTENCY: "Verify sensor commissioning/attachment",
  METADATA_INCONSISTENCY: "Verify sensor commissioning/attachment",
  CONFIG_CHANGE: "Confirm firmware/configuration change was intentional",
};

export function recommendedActionFor(issueType: string): string {
  return RECOMMENDED_ACTION[issueType] ?? "Inspect sensor connectivity";
}

// --- Decision impact (what this sensor's trust state costs downstream) -----------------

export type DecisionImpactLevel =
  "NO_IMPACT" | "CONFIDENCE_REDUCED" | "ASSESSMENT_BLOCKED" | "ACTION_BLOCKED";

export const DECISION_IMPACT_LABEL: Record<DecisionImpactLevel, string> = {
  NO_IMPACT: "No impact",
  CONFIDENCE_REDUCED: "Confidence reduced",
  ASSESSMENT_BLOCKED: "Assessment blocked",
  ACTION_BLOCKED: "Action blocked",
};

/** `ACTION_BLOCKED` is a strictly worse outcome than `ASSESSMENT_BLOCKED` (a blocked
 * action implies the assessment behind it is also blocked — see `decisionImpactFor`), so
 * a sensor's `impact.level` is never *exactly* `ASSESSMENT_BLOCKED` once it also reaches
 * `ACTION_BLOCKED`. Filtering by strict equality would make the "Assessment blocked"
 * filter structurally always empty under this policy — this treats it as "at least
 * assessment-blocked" instead, consistent with how the fleet-summary tiles already count
 * it (`machineBlockLevel(...) !== "NONE"`). */
export function matchesImpactFilter(
  level: DecisionImpactLevel,
  filter: DecisionImpactLevel | "",
): boolean {
  if (!filter) return true;
  if (filter === "ASSESSMENT_BLOCKED") {
    return level === "ASSESSMENT_BLOCKED" || level === "ACTION_BLOCKED";
  }
  return level === filter;
}

export interface DecisionImpact {
  level: DecisionImpactLevel;
  conditionImpact: string;
  mlImpact: string;
  actionImpact: string;
}

/**
 * Derived independently from two real read models — condition intelligence
 * (`fleetBucket`, was this machine's assessment itself gated by data quality) and
 * action-readiness (`readinessModeFor`'s output, was the recommended action blocked) —
 * rather than assuming one implies the other. Today, under
 * `condition_intelligence_v1.yaml`'s policy, a data-quality-gated assessment always also
 * blocks the action (see `lib/action-readiness.ts`), so the two levels currently coincide;
 * computing them from their own source instead of hard-coding that coincidence keeps this
 * correct if that policy ever changes.
 */
export type MachineBlockLevel = "ACTION_BLOCKED" | "ASSESSMENT_BLOCKED" | "NONE";

/** Machine-level fact, independent of any one sensor: is this machine's condition
 * assessment itself gated by data quality, and separately, does its action-readiness mode
 * reflect that. Two real read models (condition intelligence, action-readiness), each
 * checked on its own terms rather than one assumed from the other. */
export function machineBlockLevel(
  machineCondition:
    Pick<ConditionAssessmentResponse, "condition_type" | "lifecycle_state"> | undefined,
  actionMode: ReadinessMode | undefined,
): MachineBlockLevel {
  const assessmentBlocked = machineCondition
    ? fleetBucket(machineCondition) === "data_quality"
    : false;
  if (!assessmentBlocked) return "NONE";
  return actionMode === "BLOCKED_INSUFFICIENT_EVIDENCE" ? "ACTION_BLOCKED" : "ASSESSMENT_BLOCKED";
}

export function decisionImpactFor(
  sensorQualityState: QualityState,
  machineCondition:
    Pick<ConditionAssessmentResponse, "condition_type" | "lifecycle_state"> | undefined,
  actionMode: ReadinessMode | undefined,
): DecisionImpact {
  if (sensorQualityState === "TRUSTED") {
    return {
      level: "NO_IMPACT",
      conditionImpact: "Full evidence available",
      mlImpact: "Eligible where applicable",
      actionImpact: "Not restricted by data quality",
    };
  }
  const block = machineBlockLevel(machineCondition, actionMode);

  if (block === "ACTION_BLOCKED") {
    return {
      level: "ACTION_BLOCKED",
      conditionImpact: "Condition confidence reduced",
      mlImpact: "Inference unavailable or degraded",
      actionImpact: "Blocked — insufficient evidence",
    };
  }
  if (block === "ASSESSMENT_BLOCKED") {
    return {
      level: "ASSESSMENT_BLOCKED",
      conditionImpact: "Condition confidence reduced",
      mlImpact: "Inference unavailable or degraded",
      actionImpact: "Restricted pending data-quality recovery",
    };
  }
  return {
    level: "CONFIDENCE_REDUCED",
    conditionImpact:
      sensorQualityState === "USABLE_WITH_CAUTION"
        ? "Included with reduced confidence"
        : "Evidence excluded from this reading",
    mlImpact:
      sensorQualityState === "USABLE_WITH_CAUTION"
        ? "Eligible with caution"
        : "Input excluded from this reading",
    actionImpact: "Not currently restricting action readiness",
  };
}

/** Default table order (CLAUDE.md §25): assessments/actions this sensor's own state
 * contributes to blocking sort first, then untrusted, then caution, then trusted; most
 * recently updated first within each group. A trusted sensor is never sorted as
 * "blocking" even on a blocked machine — the block is a property of the *other* sensors on
 * that machine, not this one. */
export function sortSensorRecords(
  records: SensorQualityRecordResponse[],
  blockByMachine: Map<string, MachineBlockLevel>,
): SensorQualityRecordResponse[] {
  const stateRank: Record<QualityState, number> = {
    UNUSABLE: 0,
    USABLE_WITH_CAUTION: 1,
    TRUSTED: 2,
  };
  const blockRank: Record<MachineBlockLevel, number> = {
    ACTION_BLOCKED: 0,
    ASSESSMENT_BLOCKED: 1,
    NONE: 2,
  };
  const groupOf = (record: SensorQualityRecordResponse): number => {
    if (record.state.quality_state === "TRUSTED") return 2 + blockRank.NONE;
    const block = (record.machine_id && blockByMachine.get(record.machine_id)) || "NONE";
    return blockRank[block];
  };
  return [...records].sort((a, b) => {
    const groupA = groupOf(a);
    const groupB = groupOf(b);
    if (groupA !== groupB) return groupA - groupB;
    const stateA = stateRank[a.state.quality_state];
    const stateB = stateRank[b.state.quality_state];
    if (stateA !== stateB) return stateA - stateB;
    return new Date(b.state.updated_at).getTime() - new Date(a.state.updated_at).getTime();
  });
}
