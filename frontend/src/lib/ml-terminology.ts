import { humanize } from "@/lib/terminology";

/** Human product name for each registered model — the technical id stays available as
 * secondary detail (never hidden, per CLAUDE.md's provenance requirement), just never the
 * lead label. Falls back to a generic humanization for any model_id not listed here rather
 * than silently omitting a model this page hasn't been told the display name for. */
const MODEL_DISPLAY_NAMES: Record<string, string> = {
  FAILURE_CLASSIFICATION_BASELINE_V1: "Failure Pattern Classifier — Baseline",
  FAILURE_CLASSIFICATION_V1: "Failure Pattern Classifier — Experimental",
  LUBRICATION_ANOMALY_V1: "Lubrication Anomaly Detector",
};

export function modelDisplayName(modelId: string): string {
  return MODEL_DISPLAY_NAMES[modelId] ?? humanize(modelId);
}

/** The 8-class label schema `ml-service/ml_service/domain/labels.py` trains against —
 * product-facing phrasing of each class, distinct from (and more specific than) the
 * generic ConditionType this class may map to in Condition Intelligence. */
const FAILURE_LABEL_NAMES: Record<string, string> = {
  NORMAL: "Normal behavior",
  RESTRICTION: "Restricted lubricant delivery",
  BLOCKAGE: "Delivery blockage",
  LEAKAGE: "Possible leakage",
  PUMP_DEGRADATION: "Pump performance degradation",
  INDEPENDENT_BEARING_ISSUE: "Independent bearing condition",
  SENSOR_FAULT: "Sensor/data quality fault",
  UNKNOWN: "Not confidently any modeled class",
};

export function failureLabelName(label: string): string {
  return FAILURE_LABEL_NAMES[label] ?? humanize(label);
}

/** Feature keys are `signal.statistic.window` dot-paths (Phase 10 feature catalog) — e.g.
 * `pressure.rolling_median.15m`, `reservoir_level.relative_difference`,
 * `context.operating_state`. Humanizes each segment and re-joins with an en dash, never
 * inventing a description the model itself didn't compute. */
export function humanizeFeatureName(feature: string): string {
  return feature
    .split(".")
    .map((segment) => humanize(segment))
    .join(" — ");
}

/** Coarse signal-family grouping for the feature key's first segment — used to cluster
 * "what did the model see" into product-recognizable groups (section 10) rather than one
 * flat alphabetical list. Falls back to the humanized raw segment for anything not listed. */
const SIGNAL_GROUP_NAMES: Record<string, string> = {
  pressure: "Pressure behavior",
  flow: "Delivery behavior",
  pump_current: "Pump behavior",
  reservoir_level: "Reservoir behavior",
  bearing_temp: "Bearing behavior",
  vibration_rms: "Bearing behavior",
  vibration_peak: "Bearing behavior",
  rpm: "Operating context",
  load: "Operating context",
  cross: "Cross-signal relationships",
  context: "Operating context",
  quality: "Data quality",
  availability: "Sensor availability",
  cycle_completion: "Delivery behavior",
  piston_movement: "Delivery behavior",
  lubricant_temperature: "Delivery behavior",
};

export function signalGroupFor(feature: string): string {
  const [head] = feature.split(".");
  return SIGNAL_GROUP_NAMES[head] ?? humanize(head);
}

/** Mirrors `condition_intelligence_v1.yaml`'s `ml_classification_map` (backend policy) —
 * which ConditionType each classifier label votes toward, when deciding whether a
 * specific inference result agrees with the machine's actual persisted condition.
 * UNKNOWN is deliberately absent there too: an UNKNOWN classification abstains. */
const CLASSIFICATION_CONDITION_HINT: Record<string, string> = {
  RESTRICTION: "DEVELOPING_RESTRICTION_PATTERN",
  BLOCKAGE: "DELIVERY_BLOCKAGE_PATTERN",
  LEAKAGE: "POSSIBLE_LEAKAGE_PATTERN",
  PUMP_DEGRADATION: "PUMP_PERFORMANCE_DEGRADATION",
  SENSOR_FAULT: "SENSOR_OR_DATA_QUALITY_LIMITATION",
  INDEPENDENT_BEARING_ISSUE: "INDEPENDENT_BEARING_CONDITION",
  NORMAL: "NORMAL_OPERATION",
};

export function classificationConditionHint(label: string): string | null {
  return CLASSIFICATION_CONDITION_HINT[label] ?? null;
}

export type MLRole =
  | "PRIMARY_SUPPORTING_EVIDENCE"
  | "SUPPORTING_EVIDENCE"
  | "CORROBORATING_EVIDENCE"
  | "EXPERIMENTAL_EVIDENCE"
  | "NO_ML_EVIDENCE"
  | "BLOCKED_BY_DATA_QUALITY";

export const ML_ROLE_LABEL: Record<MLRole, string> = {
  PRIMARY_SUPPORTING_EVIDENCE: "Primary supporting evidence",
  SUPPORTING_EVIDENCE: "Supporting evidence",
  CORROBORATING_EVIDENCE: "Corroborating evidence",
  EXPERIMENTAL_EVIDENCE: "Experimental evidence — not used for decision",
  NO_ML_EVIDENCE: "No ML evidence required",
  BLOCKED_BY_DATA_QUALITY: "Blocked by data quality",
};

/** Mirrors `ConditionEngine._evidence_from_ml_result`'s real strength logic (backend) —
 * re-derived here from the same two real facts that logic uses (does this model's
 * *current* registry status clear the decision-grade bar, and how confident was this
 * specific result), not a separate invented rule. `agreesWithCondition` additionally
 * checks whether this result's own condition_hint is the one the machine's persisted
 * condition actually settled on — real classifier evidence that pointed elsewhere is
 * corroborating at best, never "primary", even if the model is servable. */
export function mlRoleFor(params: {
  status: "OK" | "INSUFFICIENT_FEATURES" | "UNKNOWN";
  modelServable: boolean;
  confidenceCategory: "LOW" | "MODERATE" | "HIGH" | null;
  agreesWithCondition: boolean | null;
}): MLRole {
  if (params.status === "INSUFFICIENT_FEATURES") return "BLOCKED_BY_DATA_QUALITY";
  if (!params.modelServable) return "EXPERIMENTAL_EVIDENCE";
  if (params.status === "UNKNOWN") return "CORROBORATING_EVIDENCE";
  const confident =
    params.confidenceCategory === "HIGH" || params.confidenceCategory === "MODERATE";
  if (params.agreesWithCondition === false) return "CORROBORATING_EVIDENCE";
  if (confident && params.agreesWithCondition) return "PRIMARY_SUPPORTING_EVIDENCE";
  if (confident) return "SUPPORTING_EVIDENCE";
  return "CORROBORATING_EVIDENCE";
}

/** The ML Intelligence "Fleet Evidence" machine selector's option list (Enterprise
 * Product Rebuild Pass 2 §8) — defaults to assets WITH ML evidence only; a no-evidence
 * machine only appears when the user opts into "All assets", or when it's the currently
 * selected machine via a deep link (so an incoming `?machineId=` never silently resolves
 * to a mismatched dropdown value). Pure so the default-exclusion behavior is unit
 * testable without mounting the whole page. */
export function selectableMachinesFor<M extends { id: string }>(params: {
  allMachines: M[];
  machinesWithEvidence: M[];
  showAllAssets: boolean;
  effectiveMachineId: string;
}): M[] {
  const base = params.showAllAssets ? params.allMachines : params.machinesWithEvidence;
  if (base.some((m) => m.id === params.effectiveMachineId)) return base;
  const deepLinked = params.allMachines.find((m) => m.id === params.effectiveMachineId);
  return deepLinked ? [...base, deepLinked] : base;
}
