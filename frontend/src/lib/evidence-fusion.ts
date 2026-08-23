import { classificationConditionHint, mlRoleFor, type MLRole } from "@/lib/ml-terminology";
import { SERVABLE_MODEL_STATUSES } from "@/lib/terminology";
import type { ConditionAssessmentResponse } from "@/lib/api/intelligence-types";
import type { MLInferenceResultResponse } from "@/lib/api/ml-types";

/** How strongly one evidence source contributed to a machine's current condition —
 * shown in the Evidence Fusion diagram (ML productization pass, item 10). These five
 * values are a presentation-layer relabeling of real backend facts (never a new judgment
 * call invented in the frontend): `ConditionEngine`/`synthesize()`'s own
 * STRONG/SUPPORTING/WEAK/EXPERIMENTAL evidence-item strengths, `MLRole`, and
 * `data_trustworthiness`, all of which are already persisted on the `ConditionAssessment`
 * the page fetches. */
export type FusionStrength = "STRONG" | "SUPPORTING" | "LIMITED" | "UNAVAILABLE" | "NOT_REQUIRED";

export const FUSION_STRENGTH_LABEL: Record<FusionStrength, string> = {
  STRONG: "Strong",
  SUPPORTING: "Supporting",
  LIMITED: "Limited",
  UNAVAILABLE: "Unavailable",
  NOT_REQUIRED: "Not required",
};

export const FUSION_STRENGTH_TONE: Record<FusionStrength, "ok" | "warn" | "info" | "neutral"> = {
  STRONG: "ok",
  SUPPORTING: "info",
  LIMITED: "warn",
  UNAVAILABLE: "neutral",
  NOT_REQUIRED: "neutral",
};

const FUSION_STRENGTH_RANK: FusionStrength[] = [
  "STRONG",
  "SUPPORTING",
  "LIMITED",
  "UNAVAILABLE",
  "NOT_REQUIRED",
];

/** Picks the best-of among several real strengths (e.g. this machine has both an anomaly
 * result and a classifier result feeding fusion) — "best contribution wins" mirrors how
 * `synthesize()` itself only needs one tallied vote to matter, never an average that would
 * dilute one genuinely strong source with another that happened to be unavailable. */
export function combineFusionStrength(strengths: FusionStrength[]): FusionStrength {
  const present = strengths.filter((s) => s !== "NOT_REQUIRED");
  if (present.length === 0) return "NOT_REQUIRED";
  return present.reduce((best, s) =>
    FUSION_STRENGTH_RANK.indexOf(s) < FUSION_STRENGTH_RANK.indexOf(best) ? s : best,
  );
}

/** Real evidence-source description sentences are `item.description` strings persisted
 * verbatim into `evidence_summary.why`/`supporting_evidence`/`contradicting_evidence`
 * (`ConditionEngine._evidence_from_rule_finding`/`_evidence_from_state_estimate` — each
 * starts with a fixed, source-specific prefix: "Rule finding ", "State estimate ",
 * "ML classifier "/"ML anomaly model "). Matching by that real prefix is the same pattern
 * the ML page's own `mlWhyLines` already uses — never an invented heuristic. */
function matchesPrefix(lines: string[], prefixes: string[]): boolean {
  return lines.some((line) => prefixes.some((prefix) => line.startsWith(prefix)));
}

function presenceStrength(
  ids: string[],
  evidence: ConditionAssessmentResponse["evidence_summary"],
  prefixes: string[],
  emptyStrength: FusionStrength,
): FusionStrength {
  if (ids.length === 0) return emptyStrength;
  if (matchesPrefix(evidence.contradicting_evidence, prefixes)) return "LIMITED";
  if (matchesPrefix(evidence.supporting_evidence, prefixes)) return "STRONG";
  if (matchesPrefix(evidence.why, prefixes)) return "SUPPORTING";
  // The id was recorded (real evidence was gathered) but its description text didn't land
  // in any of the three buckets above (e.g. a WEAK/abstaining item) — still real, checked
  // evidence, just not one that helped decide the condition either way.
  return "SUPPORTING";
}

/** No active rule finding is a real, checked state (rules are threshold-triggered, not
 * continuously scored) — absent evidence here means "nothing crossed a threshold", not
 * "this source is broken", so the empty case reads as NOT_REQUIRED rather than
 * UNAVAILABLE. */
export function ruleEvidenceStrength(
  condition: Pick<ConditionAssessmentResponse, "rule_finding_ids" | "evidence_summary">,
): FusionStrength {
  return presenceStrength(
    condition.rule_finding_ids,
    condition.evidence_summary,
    ["Rule finding "],
    "NOT_REQUIRED",
  );
}

/** Unlike rule findings, a missing state estimate usually means the Kalman filter hasn't
 * produced a trustworthy estimate yet (cold start, missing prerequisite signals) rather
 * than "nothing to estimate" — so the empty case reads as UNAVAILABLE. */
export function stateEstimateStrength(
  condition: Pick<ConditionAssessmentResponse, "state_estimate_ids" | "evidence_summary">,
): FusionStrength {
  return presenceStrength(
    condition.state_estimate_ids,
    condition.evidence_summary,
    ["State estimate "],
    "UNAVAILABLE",
  );
}

/** Mirrors `ConditionEngine`'s own `_overall_quality_state` (backend) — TRUSTED/CAUTION/
 * NO_TRUSTED_DATA/UNTRUSTED are the only real values it ever persists. */
export function dataTrustFusionStrength(dataTrustworthiness: string): FusionStrength {
  switch (dataTrustworthiness) {
    case "TRUSTED":
      return "STRONG";
    case "CAUTION":
      return "LIMITED";
    case "NO_TRUSTED_DATA":
    case "UNTRUSTED":
      return "UNAVAILABLE";
    default:
      return "UNAVAILABLE";
  }
}

export function mlRoleToFusionStrength(role: MLRole): FusionStrength {
  switch (role) {
    case "PRIMARY_SUPPORTING_EVIDENCE":
      return "STRONG";
    case "SUPPORTING_EVIDENCE":
      return "SUPPORTING";
    case "CORROBORATING_EVIDENCE":
      return "LIMITED";
    case "EXPERIMENTAL_EVIDENCE":
      return "LIMITED";
    case "BLOCKED_BY_DATA_QUALITY":
      return "UNAVAILABLE";
    case "NO_ML_EVIDENCE":
      return "NOT_REQUIRED";
  }
}

/** Real ML contribution to THIS machine's current condition, re-derived from the same two
 * models `ConditionEngine._ML_MODEL_IDS` actually wires into fusion
 * (`LUBRICATION_ANOMALY_V1`, `FAILURE_CLASSIFICATION_V1` — deliberately never the baseline
 * classifier, see `condition_engine.py`'s own comment on why). Never invents a strength for
 * a model that isn't one of those two, even if it has a real persisted result. */
export function machineMlFusionStrength(
  results: MLInferenceResultResponse[],
  condition: ConditionAssessmentResponse | undefined,
  modelStatusById: Map<string, string>,
): FusionStrength {
  const servable = (modelId: string) =>
    modelStatusById.has(modelId) && SERVABLE_MODEL_STATUSES.has(modelStatusById.get(modelId)!);

  const anomaly = results.find((r) => r.model_id === "LUBRICATION_ANOMALY_V1") ?? null;
  const classifier = results.find((r) => r.model_id === "FAILURE_CLASSIFICATION_V1") ?? null;

  const roles: MLRole[] = [];
  if (anomaly) {
    roles.push(
      mlRoleFor({
        status: anomaly.status,
        modelServable: servable(anomaly.model_id),
        confidenceCategory: null,
        agreesWithCondition: null,
      }),
    );
  }
  if (classifier) {
    const agrees = condition
      ? classificationConditionHint(classifier.predicted_class ?? "") === condition.condition_type
      : null;
    roles.push(
      mlRoleFor({
        status: classifier.status,
        modelServable: servable(classifier.model_id),
        confidenceCategory: classifier.confidence_category,
        agreesWithCondition: agrees,
      }),
    );
  }
  if (roles.length === 0) return "NOT_REQUIRED";
  return combineFusionStrength(roles.map(mlRoleToFusionStrength));
}
