/**
 * Centralized status vocabulary (Phase 29 brief §29.4 — "Do not use conflicting labels
 * for the same concept"). Every page that renders a condition/confidence/priority/
 * quality/severity value should go through here rather than re-deriving its own tone/
 * label mapping — several pages had copy-pasted, subtly different versions of this
 * before Phase 28/29 consolidated them (ADR-158).
 */

export type Tone = "ok" | "warn" | "error" | "info" | "neutral";

/** SNAKE_CASE / UPPER_CASE enum value -> readable "Title Case" label. Never hides the
 * underlying value from technical/audit contexts — only used for primary product copy. */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function shortId(id: string | null | undefined, length = 8): string {
  if (!id) return "—";
  return id.slice(0, length);
}

// --- Condition severity -----------------------------------------------------------

export function severityTone(value: string): Tone {
  if (value === "INFO") return "ok";
  if (value === "WARNING") return "warn";
  if (value === "HIGH") return "warn";
  if (value === "CRITICAL") return "error";
  return "neutral";
}

// --- Confidence (condition / decision) ---------------------------------------------

export function confidenceTone(value: string): Tone {
  if (value === "HIGH") return "ok";
  if (value === "MODERATE") return "warn";
  if (value === "LOW") return "neutral";
  return "neutral";
}

// --- Decision priority ---------------------------------------------------------------

export function priorityTone(value: string): Tone {
  if (value === "MONITOR") return "ok";
  if (value === "PLANNED") return "neutral";
  if (value === "HIGH") return "warn";
  if (value === "URGENT") return "error";
  return "neutral";
}

// --- Data quality (sensor/telemetry) -------------------------------------------------

const QUALITY_TRUSTED = new Set(["GOOD", "TRUSTED", "ACTIVE"]);
const QUALITY_CAUTION = new Set([
  "UNCERTAIN",
  "SUSPECT",
  "COMMUNICATION_LOSS",
  "STALE",
  "BUILDING",
]);
const QUALITY_UNUSABLE = new Set(["BAD", "INVALID", "MISSING", "UNAVAILABLE", "INVALIDATED"]);

export function qualityTone(value: string): Tone {
  if (QUALITY_TRUSTED.has(value)) return "ok";
  if (QUALITY_CAUTION.has(value)) return "warn";
  if (QUALITY_UNUSABLE.has(value)) return "error";
  return "neutral";
}

export function qualityLabel(value: string): string {
  if (QUALITY_TRUSTED.has(value)) return "Trusted";
  if (QUALITY_UNUSABLE.has(value)) return "Unusable";
  if (QUALITY_CAUTION.has(value)) return "Usable with caution";
  return humanize(value);
}

// --- State estimation trend -----------------------------------------------------------

export function stateTrendTone(value: string): Tone {
  if (value === "IMPROVING") return "ok";
  if (value === "DETERIORATING") return "warn";
  if (value === "STABLE") return "neutral";
  return "neutral";
}

// --- ML model lifecycle status (Phase 11/32 registry) ------------------------------
// Never a claim this UI is entitled to promote a model past what the registry itself
// says — this only maps the registry's own status string to a display tone.

export function modelStatusTone(value: string): Tone {
  if (value === "PRODUCTION" || value === "VALIDATED") return "ok";
  if (value === "STAGING") return "warn";
  if (value === "EXPERIMENT") return "neutral";
  if (value === "RETIRED" || value === "REJECTED") return "error";
  return "neutral";
}

export const SERVABLE_MODEL_STATUSES = new Set(["VALIDATED", "STAGING", "PRODUCTION"]);

// --- Incident / lifecycle state -------------------------------------------------------

export function incidentStateTone(value: string): Tone {
  if (value === "RESOLVED" || value === "CLOSED") return "ok";
  if (value === "OPEN" || value === "DETECTED") return "error";
  return "warn";
}

export function maintenanceStateTone(value: string): Tone {
  if (value === "COMPLETED") return "ok";
  if (value === "CANCELLED") return "neutral";
  if (value === "REVIEW_REQUIRED") return "error";
  return "warn";
}

export function feedbackTone(value: string): Tone {
  if (value === "TRUE_POSITIVE") return "ok";
  if (value === "FALSE_POSITIVE") return "error";
  if (value === "MISSED_FAILURE") return "error";
  return "neutral";
}

/** Human meaning first — "TRUE_POSITIVE" on its own tells a reviewer nothing; this is
 * what the classification actually means for the diagnosis. */
export function feedbackHeadline(value: string): string {
  switch (value) {
    case "TRUE_POSITIVE":
      return "Diagnosis confirmed by maintenance";
    case "FALSE_POSITIVE":
      return "Diagnosis not confirmed by maintenance";
    case "MISSED_FAILURE":
      return "A failure was missed by this diagnosis";
    case "INCONCLUSIVE":
      return "Outcome inconclusive";
    default:
      return humanize(value);
  }
}

export function customerStatusTone(value: string): Tone {
  if (value === "HEALTHY") return "ok";
  if (value === "ATTENTION_REQUIRED") return "error";
  if (value === "DEGRADED_VISIBILITY" || value === "MAINTENANCE_ACTIVE") return "warn";
  return "neutral";
}

export function provenanceTone(value: string): Tone {
  if (value === "MEASURED_PLATFORM_METRIC") return "ok";
  if (value === "DEMO_ESTIMATE") return "warn";
  return "neutral";
}

export function actorTone(value: string): Tone {
  if (value === "HUMAN") return "ok";
  if (value === "AGENT") return "warn";
  return "neutral";
}

// --- Generic asset status/criticality (used broadly across hierarchy pages) --------

const STATUS_ERROR = new Set(["CRITICAL", "OFFLINE", "FAULTY", "SUSPENDED", "RETIRED"]);
const STATUS_WARN = new Set(["HIGH", "MAINTENANCE", "DEGRADED", "COMMISSIONING", "PILOT"]);
const STATUS_NEUTRAL = new Set([
  "REGISTERED",
  "INACTIVE",
  "DECOMMISSIONED",
  "PLANNED",
  "UNKNOWN",
  "PROSPECT",
]);

// --- Commissioning / capability / compatibility -------------------------------------

export function commissioningStatusTone(value: string): Tone {
  if (value === "COMPLETED" || value === "READY") return "ok";
  if (value === "FAILED") return "error";
  return "warn";
}

export function capabilityLevelTone(value: string): Tone {
  if (value === "FULL_INTELLIGENCE") return "ok";
  if (value === "NONE") return "error";
  return "warn";
}

export function compatibilityTone(value: string): Tone {
  if (value === "SUPPORTED") return "ok";
  if (value === "INCOMPATIBLE") return "error";
  if (value === "SUPPORTED_WITH_LIMITATIONS") return "warn";
  return "neutral";
}

export function toneForStatus(value: string): Tone {
  if (STATUS_ERROR.has(value)) return "error";
  if (STATUS_WARN.has(value)) return "warn";
  if (STATUS_NEUTRAL.has(value)) return "neutral";
  return "ok";
}

// --- Portfolio Intelligence (organization/site/area performance, ADR-177) ----------
// These map the backend's own categorical enums 1:1 — never a value this layer invents.

export function portfolioPriorityTone(value: string): Tone {
  if (value === "CRITICAL_ATTENTION") return "error";
  if (value === "HIGH_ATTENTION" || value === "ATTENTION") return "warn";
  if (value === "MONITOR") return "ok";
  return "neutral"; // DATA_LIMITED
}

export function actionReadinessStateTone(value: string): Tone {
  if (value === "MONITORING_ONLY") return "ok";
  if (value === "HUMAN_ACTION_REQUIRED") return "warn";
  if (value === "ASSESSMENT_BLOCKED") return "error";
  return "neutral"; // DATA_LIMITED / NOT_YET_ASSESSED
}

export function energyBucketTone(value: string): Tone {
  if (value === "NORMAL_ENERGY_BEHAVIOR" || value === "QUALIFIED_ENERGY_RECOVERY") return "ok";
  if (value === "ACTIVE_ELEVATED_ENERGY" || value === "ATTRIBUTION_SUPPORTED_OPPORTUNITY") {
    return "warn";
  }
  if (value === "OUTCOME_AWAITING_VERIFICATION") return "info";
  if (value === "OUTCOME_DETERIORATED") return "error";
  return "neutral"; // INCONCLUSIVE_OUTCOME / INSUFFICIENT_ENERGY_DATA
}

export function maintenanceOutcomeBucketTone(value: string): Tone {
  if (value === "COMPLETED_QUALIFIED_RECOVERY" || value === "COMPLETED_PROBABLE_RECOVERY") {
    return "ok";
  }
  if (value === "OPEN_ACTION") return "warn";
  if (value === "COMPLETED_OUTCOME_NOT_ASSESSED") return "info";
  if (value === "COMPLETED_DETERIORATED") return "error";
  return "neutral"; // COMPLETED_NO_MATERIAL_CHANGE / COMPLETED_INCONCLUSIVE
}

export function dataTrustCategoryTone(value: string): Tone {
  if (value === "DECISION_EVIDENCE_TRUSTED") return "ok";
  if (value === "CONFIDENCE_REDUCED") return "warn";
  if (value === "ASSESSMENT_BLOCKED" || value === "ACTION_BLOCKED") return "error";
  return "neutral";
}

export function portfolioOutcomeTone(value: string): Tone {
  if (
    value === "CONDITION_RESOLVED" ||
    value === "QUALIFIED_ENERGY_RECOVERY" ||
    value === "MAINTENANCE_COMPLETED"
  ) {
    return "ok";
  }
  if (value === "CONDITION_IMPROVING") return "info";
  return "neutral"; // CARBON_ESTIMATE_PRODUCED
}
