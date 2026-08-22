import { conditionInterpretation } from "@/lib/condition-interpretation";
import { fleetBucket } from "@/lib/fleet-condition";
import { humanize } from "@/lib/terminology";
import type { Tone } from "@/lib/terminology";
import type {
  ConditionAssessmentResponse,
  DecisionAssessmentResponse,
} from "@/lib/api/intelligence-types";

/**
 * The six readiness modes this platform will ever show (CLAUDE.md's condition-driven
 * control boundary). `AUTO_ELIGIBLE_SIMULATION` and `BLOCKED_SAFETY_INTERLOCK` are real,
 * live-computed classifications — not placeholders — but neither is reachable by any
 * machine in the current 10-asset demo fleet, and that absence is itself the honest
 * story: every `RecommendedAction` in this reference implementation
 * (`backend/app/domain/enums.py`) is a human physical-presence inspection/verification
 * step, never a control command, so nothing is structurally eligible for automation yet;
 * every machine's `status` is `MONITORED`, so no interlock is currently active. Both
 * modes are explained in the on-page legend so a reviewer sees the concept even when no
 * row currently occupies it.
 */
export type ReadinessMode =
  | "MONITORING_ONLY"
  | "MANUAL_ACTION_REQUIRED"
  | "HUMAN_APPROVAL_REQUIRED"
  | "AUTO_ELIGIBLE_SIMULATION"
  | "BLOCKED_INSUFFICIENT_EVIDENCE"
  | "BLOCKED_SAFETY_INTERLOCK";

export const READINESS_MODE_LABEL: Record<ReadinessMode, string> = {
  MONITORING_ONLY: "Monitoring only",
  MANUAL_ACTION_REQUIRED: "Manual action required",
  HUMAN_APPROVAL_REQUIRED: "Human approval required",
  AUTO_ELIGIBLE_SIMULATION: "Auto-eligible — simulation only",
  BLOCKED_INSUFFICIENT_EVIDENCE: "Blocked — insufficient evidence",
  BLOCKED_SAFETY_INTERLOCK: "Blocked — safety/interlock",
};

export const READINESS_MODE_DESCRIPTION: Record<ReadinessMode, string> = {
  MONITORING_ONLY: "No action currently warranted — condition reads normal.",
  MANUAL_ACTION_REQUIRED: "A technician should perform the recommended action manually.",
  HUMAN_APPROVAL_REQUIRED:
    "Evidence supports a recommendation, but it requires human sign-off before proceeding.",
  AUTO_ELIGIBLE_SIMULATION:
    "Policy criteria indicate this action class could be eligible for automated execution in a future validated closed-loop deployment — simulation only, never executed.",
  BLOCKED_INSUFFICIENT_EVIDENCE:
    "Action must not be automated or strongly recommended — evidence or data quality is insufficient.",
  BLOCKED_SAFETY_INTERLOCK:
    "Action is not permitted — the asset is not in a normal monitored operating state.",
};

export const READINESS_MODE_TONE: Record<ReadinessMode, Tone> = {
  MONITORING_ONLY: "ok",
  MANUAL_ACTION_REQUIRED: "warn",
  HUMAN_APPROVAL_REQUIRED: "error",
  AUTO_ELIGIBLE_SIMULATION: "info",
  BLOCKED_INSUFFICIENT_EVIDENCE: "neutral",
  BLOCKED_SAFETY_INTERLOCK: "neutral",
};

const NON_OPERATIONAL_STATUSES = new Set([
  "COMMISSIONING",
  "BASELINING",
  "MAINTENANCE",
  "OFFLINE",
  "RETIRED",
  "REGISTERED",
]);

/**
 * No recommended action in this platform's taxonomy is itself a physical control
 * command (`RecommendedAction` in `backend/app/domain/enums.py` — inspect/verify/check
 * actions only), so `AUTO_ELIGIBLE_SIMULATION` is deliberately never derived here from
 * live data. It stays in the type/legend as an honest statement of what a future,
 * genuinely-automatable action taxonomy would need, not a currently-reachable state.
 */
export function readinessModeFor(
  condition: Pick<ConditionAssessmentResponse, "condition_type" | "lifecycle_state">,
  decision: DecisionAssessmentResponse | null,
  machineStatus: string,
): ReadinessMode {
  if (NON_OPERATIONAL_STATUSES.has(machineStatus)) return "BLOCKED_SAFETY_INTERLOCK";
  const bucket = fleetBucket(condition);
  if (bucket === "insufficient_evidence" || bucket === "data_quality") {
    return "BLOCKED_INSUFFICIENT_EVIDENCE";
  }
  // A confidently normal condition is always monitoring-only, regardless of what the
  // last-persisted decision says — that decision may predate the machine's own recovery
  // (decisions are only recomputed on demand, unlike the condition re-check
  // `MaintenanceService.complete()` always performs), and re-surfacing a stale
  // pre-resolution "inspect X" recommendation next to a Normal Operation condition would
  // misrepresent what this machine currently needs.
  if (bucket === "healthy") return "MONITORING_ONLY";
  if (!decision || !decision.human_review_required) return "MONITORING_ONLY";
  if (decision.priority === "URGENT" || decision.priority === "HIGH") {
    return "HUMAN_APPROVAL_REQUIRED";
  }
  return "MANUAL_ACTION_REQUIRED";
}

/** The recommended action to actually display — `CONTINUE_MONITORING` for a confidently
 * normal condition even if the last-persisted `DecisionAssessment` predates recovery and
 * still names an inspection action (see `readinessModeFor`'s healthy-bucket note); the
 * mapping itself is real, deterministic policy (`NORMAL_OPERATION: CONTINUE_MONITORING`
 * in `decision_intelligence_v1.yaml`), not a guess. */
export function effectiveRecommendedAction(
  condition: Pick<ConditionAssessmentResponse, "condition_type" | "lifecycle_state">,
  decision: DecisionAssessmentResponse | null,
): { action: string; priority: string } | null {
  if (fleetBucket(condition) === "healthy") {
    return { action: "CONTINUE_MONITORING", priority: "MONITOR" };
  }
  if (!decision) return null;
  return { action: decision.recommended_action, priority: decision.priority };
}

export interface ReadinessEvidenceItem {
  label: string;
  value: string;
}

/**
 * The prerequisite checklist behind one machine's readiness mode — every value traces to
 * a real persisted field (condition/decision/machine status), never an invented
 * rationale. `Physical actuation` is the one constant line: it states a true fact about
 * this reference platform (no actuator interface exists anywhere in it) rather than a
 * per-machine computed value, and is included on every row because it's the fact that
 * most directly explains why nothing here ever reaches automated execution.
 */
export function readinessEvidenceFor(
  condition: ConditionAssessmentResponse,
  decision: DecisionAssessmentResponse | null,
  machineStatus: string,
  mode: ReadinessMode,
): ReadinessEvidenceItem[] {
  const commissioned = !NON_OPERATIONAL_STATUSES.has(machineStatus);
  const bucket = fleetBucket(condition);
  const actionable = bucket === "attention";

  const items: ReadinessEvidenceItem[] = [
    {
      label: "Machine commissioned",
      value: commissioned ? "Yes" : `No — ${humanize(machineStatus)}`,
    },
  ];

  if (mode === "BLOCKED_SAFETY_INTERLOCK") {
    items.push({
      label: "Safety / interlock",
      value: `Active — asset must reach Monitored status before readiness applies`,
    });
    return items;
  }

  items.push(
    { label: "Data trust", value: humanize(condition.evidence_summary.data_trustworthiness) },
    { label: "Condition confidence", value: humanize(condition.confidence) },
    { label: "Current condition", value: conditionInterpretation(condition.condition_type) },
  );

  if (mode === "BLOCKED_INSUFFICIENT_EVIDENCE") {
    items.push({
      label: "Recommended next evidence",
      value:
        condition.recommended_next_evidence ??
        "Additional evidence is needed before any action recommendation is reliable.",
    });
    return items;
  }

  items.push(
    { label: "Condition actionable", value: actionable ? "Yes" : "No — normal or recovering" },
    {
      label: "Recommended action",
      value: decision ? humanize(decision.recommended_action) : "Not yet available",
    },
    {
      label: "Human approval required",
      value: decision ? (decision.human_review_required ? "Yes" : "No") : "—",
    },
    { label: "Safety / interlock", value: "Clear — asset is Monitored" },
    {
      label: "Physical actuation",
      value: "Not connected — no automated control exists in this platform",
    },
  );
  return items;
}
