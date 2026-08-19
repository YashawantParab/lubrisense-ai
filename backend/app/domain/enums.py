"""Domain enumerations shared by ORM models and API schemas.

Every enum here is a demo/reference taxonomy for this project, not a validated industrial
or commercial standard — see `docs/DOMAIN_MODEL.md` §2.3 and `docs/ASSET_HIERARCHY.md` for
the disclaimer this taxonomy is built under. All are persisted as `VARCHAR` with a CHECK
constraint (`native_enum=False` — see TECHNICAL_DECISIONS.md, enum strategy ADR), not native
Postgres enum types, so adding a new value later is a plain migration rather than an
`ALTER TYPE`.
"""

from __future__ import annotations

from enum import StrEnum


class TenantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class ServiceTier(StrEnum):
    """DEMO product packaging tiers — illustrative only, not real commercial offerings."""

    CONNECTED_MONITORING = "CONNECTED_MONITORING"
    INTELLIGENT_DIAGNOSTICS = "INTELLIGENT_DIAGNOSTICS"
    PREDICTIVE_RELIABILITY = "PREDICTIVE_RELIABILITY"
    PREMIUM_SERVICE = "PREMIUM_SERVICE"


class CommercialStatus(StrEnum):
    PROSPECT = "PROSPECT"
    PILOT = "PILOT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ENDED = "ENDED"


class Criticality(StrEnum):
    """Reusable across ProductionLine, Machine, and Bearing. No decision logic uses this
    yet — see docs/ASSET_HIERARCHY.md."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class OperationalStatus(StrEnum):
    """Generic lifecycle status for organizational/physical-component entities that don't
    need a richer state machine (Site, Plant, ProductionLine, Bearing, LubricationSystem
    components, Gateway)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DECOMMISSIONED = "DECOMMISSIONED"


class MachineStatus(StrEnum):
    """Machine has a richer lifecycle than other assets because it is the primary object
    a technician/reliability engineer tracks through onboarding."""

    REGISTERED = "REGISTERED"
    COMMISSIONING = "COMMISSIONING"
    BASELINING = "BASELINING"
    MONITORED = "MONITORED"
    MAINTENANCE = "MAINTENANCE"
    OFFLINE = "OFFLINE"
    RETIRED = "RETIRED"


class MachineType(StrEnum):
    CONVEYOR = "CONVEYOR"
    MOTOR = "MOTOR"
    FAN = "FAN"
    PUMP = "PUMP"
    COMPRESSOR = "COMPRESSOR"
    CRUSHER = "CRUSHER"


class LubricationSystemType(StrEnum):
    """Generic centralized-lubrication categories — see docs/DOMAIN_MODEL.md §2."""

    PROGRESSIVE = "PROGRESSIVE"
    SINGLE_LINE = "SINGLE_LINE"
    DUAL_LINE = "DUAL_LINE"
    MULTI_LINE = "MULTI_LINE"


class CommissioningState(StrEnum):
    PLANNED = "PLANNED"
    COMMISSIONING = "COMMISSIONING"
    COMMISSIONED = "COMMISSIONED"
    DECOMMISSIONED = "DECOMMISSIONED"


class SensorType(StrEnum):
    PRESSURE = "PRESSURE"
    FLOW = "FLOW"
    RESERVOIR_LEVEL = "RESERVOIR_LEVEL"
    PUMP_CURRENT = "PUMP_CURRENT"
    PUMP_RUNTIME = "PUMP_RUNTIME"
    CYCLE_COMPLETION = "CYCLE_COMPLETION"
    PISTON_MOVEMENT = "PISTON_MOVEMENT"
    LUBRICANT_TEMPERATURE = "LUBRICANT_TEMPERATURE"
    VIBRATION_RMS = "VIBRATION_RMS"
    VIBRATION_PEAK = "VIBRATION_PEAK"
    BEARING_TEMPERATURE = "BEARING_TEMPERATURE"
    RPM = "RPM"
    LOAD = "LOAD"


class SensorStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    FAULTY = "FAULTY"
    DECOMMISSIONED = "DECOMMISSIONED"


class SensorQualityState(StrEnum):
    """Placeholder pending the Phase 7 data-quality engine — not computed in Phase 2."""

    UNKNOWN = "UNKNOWN"
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"


class TelemetryQuality(StrEnum):
    """Per-reading quality code — mirrors `edge.domain.enums.EdgeQuality` value-for-value
    (Phase 6 defines its own copy per ADR-059, not an import of the edge package, but the
    wire values must match exactly since they cross the MQTT/Kafka boundary unchanged)."""

    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"
    INVALID = "INVALID"
    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"
    BAD = "BAD"
    UNAVAILABLE = "UNAVAILABLE"


class QuarantineReason(StrEnum):
    """Why a telemetry event was routed to `telemetry_quarantine` instead of `telemetry`.

    `SCHEMA_INVALID`/`UNSUPPORTED_SCHEMA_VERSION` are structural failures the MQTT bridge
    detects (published to the Kafka DLQ topic, then drained into this table by the
    consumer's DLQ-topic task). The rest are tenant/entity/context failures only the
    consumer can detect, since they require a database lookup.
    """

    SCHEMA_INVALID = "SCHEMA_INVALID"
    UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"
    UNKNOWN_TENANT = "UNKNOWN_TENANT"
    UNKNOWN_SENSOR = "UNKNOWN_SENSOR"
    UNKNOWN_GATEWAY = "UNKNOWN_GATEWAY"
    CROSS_TENANT_MISMATCH = "CROSS_TENANT_MISMATCH"
    CONTEXT_CONFLICT = "CONTEXT_CONFLICT"
    PERSISTENT_FAILURE = "PERSISTENT_FAILURE"


# ---------------------------------------------------------------------------
# Phase 7 — Data Quality Engine
# ---------------------------------------------------------------------------


class QualityDimension(StrEnum):
    """Which aspect of quality an issue concerns (Phase 7 brief §3) — a single event/window
    may have issues across several dimensions at once; this is never collapsed to one
    boolean."""

    COMPLETENESS = "COMPLETENESS"
    VALIDITY = "VALIDITY"
    TIMELINESS = "TIMELINESS"
    ORDERING = "ORDERING"
    CONSISTENCY = "CONSISTENCY"
    COMMUNICATION = "COMMUNICATION"
    SENSOR_HEALTH = "SENSOR_HEALTH"
    CONFIGURATION = "CONFIGURATION"
    CONTEXT = "CONTEXT"


class IssueSeverity(StrEnum):
    """Data-quality severity — deliberately distinct from any future machine-condition
    severity scale (CLAUDE.md: do not infer machine-condition severity from data-quality
    severity)."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class QualityState(StrEnum):
    """Overall trustworthiness of a sensor's current stream (Phase 7 brief §4) — data
    confidence, not equipment health. Deliberately avoids HEALTHY/FAILED wording (brief
    §38) since this describes the data, not the asset."""

    TRUSTED = "TRUSTED"
    USABLE_WITH_CAUTION = "USABLE_WITH_CAUTION"
    UNUSABLE = "UNUSABLE"


class Eligibility(StrEnum):
    """Whether a specific reading/window may be consumed by later intelligence (baselines/
    rules/ML/Kalman/ConditionEngine — Phase 7 brief §27). Derived from the same issues as
    `QualityState` but is the per-event/window consumption decision, not the sensor's
    overall trust level."""

    ELIGIBLE = "ELIGIBLE"
    ELIGIBLE_WITH_CAUTION = "ELIGIBLE_WITH_CAUTION"
    INELIGIBLE = "INELIGIBLE"


class IssueStatus(StrEnum):
    """Lifecycle of a quality issue (Phase 7 brief §49). Meaningful mainly for window/
    stream-scoped issues (staleness, communication loss, drift/stuck suspicion), which
    represent an ongoing condition that can genuinely recover. Event-scoped issues (a
    specific bad reading) are created directly as RESOLVED — see
    TECHNICAL_DECISIONS.md, issue-lifecycle-scope ADR."""

    ACTIVE = "ACTIVE"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"


class AssessmentScope(StrEnum):
    """Whether a `QualityAssessment` concerns one telemetry event or a rolling window over
    a sensor's stream (Phase 7 brief §6)."""

    EVENT = "EVENT"
    WINDOW = "WINDOW"


class QualityIssueType(StrEnum):
    """Concrete issue types, grouped by the `QualityDimension` they belong to (comment
    markers below are documentation only, not enforced)."""

    # COMPLETENESS
    MISSING_VALUE = "MISSING_VALUE"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    # VALIDITY
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INVALID_VALUE = "INVALID_VALUE"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    # TIMELINESS
    LATE_ARRIVAL = "LATE_ARRIVAL"
    VERY_LATE_ARRIVAL = "VERY_LATE_ARRIVAL"
    STALE_STREAM = "STALE_STREAM"
    CLOCK_OFFSET_SUSPECTED = "CLOCK_OFFSET_SUSPECTED"
    CLOCK_DRIFT_SUSPECTED = "CLOCK_DRIFT_SUSPECTED"
    # ORDERING
    OUT_OF_ORDER = "OUT_OF_ORDER"
    DUPLICATE_PATTERN = "DUPLICATE_PATTERN"
    # CONSISTENCY / CONTEXT
    CONTEXT_INCONSISTENCY = "CONTEXT_INCONSISTENCY"
    METADATA_INCONSISTENCY = "METADATA_INCONSISTENCY"
    # COMMUNICATION
    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"
    # SENSOR_HEALTH
    SENSOR_DRIFT_SUSPECTED = "SENSOR_DRIFT_SUSPECTED"
    STUCK_SENSOR_SUSPECTED = "STUCK_SENSOR_SUSPECTED"
    SPIKE_DETECTED = "SPIKE_DETECTED"
    # CONFIGURATION
    CONFIG_CHANGE = "CONFIG_CHANGE"


class StalenessStatus(StrEnum):
    """`SensorQualityState.staleness_status` — whether a sensor's stream is currently
    reporting within its policy-configured expected cadence (sensor-type-aware, Phase 7
    brief §13)."""

    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ClockStatus(StrEnum):
    """`SensorQualityState.clock_status` — distinguishes a constant clock offset from a
    progressive drift trend (Phase 7 brief §14); demo-configuration-based, not a claim of
    real NTP/PTP accuracy."""

    NORMAL = "NORMAL"
    OFFSET_SUSPECTED = "OFFSET_SUSPECTED"
    DRIFT_SUSPECTED = "DRIFT_SUSPECTED"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Phase 8 — Baseline Engine
# ---------------------------------------------------------------------------


class BaselineStrategyType(StrEnum):
    """How a `BaselineProfile`'s statistics were derived (Phase 8 brief §3). Not a quality
    ranking — each strategy answers a different question and the fallback hierarchy
    (`app.baselines.services.fallback`) picks among them, it does not prefer one outright."""

    STATIC_ENGINEERING_REFERENCE = "STATIC_ENGINEERING_REFERENCE"
    ROLLING_ASSET_BASELINE = "ROLLING_ASSET_BASELINE"
    CONTEXTUAL_ASSET_BASELINE = "CONTEXTUAL_ASSET_BASELINE"


class BaselineState(StrEnum):
    """Lifecycle of one `BaselineProfile` version (Phase 8 brief §15). See
    docs/BASELINES.md for the full transition diagram.

    INSUFFICIENT_DATA -> BUILDING -> ACTIVE -> {STALE, INVALIDATED, SUPERSEDED}. STALE can
    recover back to ACTIVE if fresh eligible telemetry resumes; INVALIDATED/SUPERSEDED are
    terminal for that specific version (a new version, not a resurrected old one, follows).
    """

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    BUILDING = "BUILDING"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    INVALIDATED = "INVALIDATED"
    SUPERSEDED = "SUPERSEDED"


class BaselineMetricKind(StrEnum):
    """What shape of statistics `BaselineProfile.statistics` holds — a plain numeric
    per-reading distribution is not the same shape as a depletion trend or a cycle-level
    aggregate, so this field selects which of `app.baselines.domain.*` the JSON matches
    (Phase 8 brief §12/§24/§25)."""

    STANDARD = "STANDARD"
    RESERVOIR_TREND = "RESERVOIR_TREND"
    CYCLE_METRIC = "CYCLE_METRIC"


class DeviationClassification(StrEnum):
    """Output of the explainable deviation helper (Phase 8 brief §23) — deliberately not a
    fault classification. `NOT_ENOUGH_DATA` when no ACTIVE/usable baseline could be
    resolved at all, distinct from `WITHIN_EXPECTED_RANGE`."""

    WITHIN_EXPECTED_RANGE = "WITHIN_EXPECTED_RANGE"
    MILD_DEVIATION = "MILD_DEVIATION"
    STRONG_DEVIATION = "STRONG_DEVIATION"
    NOT_ENOUGH_DATA = "NOT_ENOUGH_DATA"


class BaselineSourceKind(StrEnum):
    """Which level of the fallback hierarchy (Phase 8 brief §22) actually produced the
    baseline handed back to a caller — `app/api/v1/baselines.py` always reports this so a
    caller never mistakes a coarse fallback for an exact-context match."""

    EXACT_CONTEXT = "EXACT_CONTEXT"
    OPERATING_STATE = "OPERATING_STATE"
    SENSOR_LEVEL = "SENSOR_LEVEL"
    ENGINEERING_REFERENCE = "ENGINEERING_REFERENCE"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Phase 9 — Rules Engine
# ---------------------------------------------------------------------------


class RuleCategory(StrEnum):
    """Taxonomy grouping for `RuleFinding.category` (Phase 9 brief §9) — organizational,
    not a source of decision logic."""

    HYDRAULIC = "HYDRAULIC"
    PUMP = "PUMP"
    RESERVOIR = "RESERVOIR"
    LUBRICATION_CYCLE = "LUBRICATION_CYCLE"
    BEARING_CONDITION = "BEARING_CONDITION"
    SENSOR_QUALITY_DEPENDENT = "SENSOR_QUALITY_DEPENDENT"
    CROSS_SIGNAL = "CROSS_SIGNAL"
    CONFIGURATION = "CONFIGURATION"


class RuleFindingType(StrEnum):
    """The generic evidence-finding taxonomy (Phase 9 brief §10) — every value here is
    evidence language, never a confirmed-fault claim (see `docs/RULES_ENGINE.md` "Causal
    language"). Exactly the 17 catalog entries the brief requires, no more, no fewer."""

    FLOW_BELOW_CONTEXTUAL_BASELINE = "FLOW_BELOW_CONTEXTUAL_BASELINE"
    PRESSURE_ABOVE_CONTEXTUAL_BASELINE = "PRESSURE_ABOVE_CONTEXTUAL_BASELINE"
    PRESSURE_BUILD_SLOW = "PRESSURE_BUILD_SLOW"
    PUMP_CURRENT_ABOVE_BASELINE = "PUMP_CURRENT_ABOVE_BASELINE"
    PUMP_RUNTIME_ABOVE_BASELINE = "PUMP_RUNTIME_ABOVE_BASELINE"
    CYCLE_DURATION_ABOVE_BASELINE = "CYCLE_DURATION_ABOVE_BASELINE"
    CYCLE_COMPLETION_FAILURE = "CYCLE_COMPLETION_FAILURE"
    RESERVOIR_LEVEL_LOW = "RESERVOIR_LEVEL_LOW"
    RESERVOIR_DEPLETION_ABNORMAL = "RESERVOIR_DEPLETION_ABNORMAL"
    BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE = "BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE"
    VIBRATION_ABOVE_CONTEXTUAL_BASELINE = "VIBRATION_ABOVE_CONTEXTUAL_BASELINE"
    FLOW_PRESSURE_RESTRICTION_PATTERN = "FLOW_PRESSURE_RESTRICTION_PATTERN"
    FLOW_PRESSURE_LEAKAGE_PATTERN = "FLOW_PRESSURE_LEAKAGE_PATTERN"
    PUMP_DEGRADATION_PATTERN = "PUMP_DEGRADATION_PATTERN"
    LUBRICATION_PATH_DEGRADATION_PATTERN = "LUBRICATION_PATH_DEGRADATION_PATTERN"
    INDEPENDENT_BEARING_CONDITION_PATTERN = "INDEPENDENT_BEARING_CONDITION_PATTERN"
    INSUFFICIENT_TRUSTED_DATA = "INSUFFICIENT_TRUSTED_DATA"


class RuleFindingSeverity(StrEnum):
    """Deliberately a distinct scale from `IssueSeverity` (data-quality severity,
    INFO/WARNING/ERROR/CRITICAL) — this describes evidence about physical/equipment
    condition, never data trustworthiness (Phase 9 brief §23)."""

    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RuleFindingState(StrEnum):
    """Lifecycle of one finding lineage (Phase 9 brief §7/§29). CANDIDATE is evidence that
    has fired but not yet been confirmed stable across enough consecutive evaluation cycles
    (debounce, `docs/RULES_ENGINE.md` "Debounce and hysteresis") — a CANDIDATE that stops
    firing before confirmation resolves directly, never having been ACTIVE. ACTIVE requires
    two consecutive clean cycles (RECOVERING, then RESOLVED) to clear, avoiding flapping."""

    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"


class EvidenceStrength(StrEnum):
    """Explainable evidence strength (Phase 9 brief §8) — explicitly not an ML probability
    or a fabricated percentage. Derived from how far a value sits from its baseline, how
    many independent signals corroborate it, and how long it has persisted."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class MLResultKind(StrEnum):
    """Which `ml-service` model family produced one `MLInferenceResult` row (Phase 11
    brief §12, §15). Kept as an explicit discriminator rather than inferred from
    `model_type` so a query can cheaply filter one kind without a string-prefix match."""

    ANOMALY = "ANOMALY"
    CLASSIFICATION = "CLASSIFICATION"


class MLInferenceStatus(StrEnum):
    """Mirrors `ml_service.domain.inference.InferenceStatus` (Phase 11 brief §33-§34) —
    ML output is evidence, and evidence can be genuinely unavailable or ambiguous rather
    than forced into a confident answer."""

    OK = "OK"
    INSUFFICIENT_FEATURES = "INSUFFICIENT_FEATURES"
    UNKNOWN = "UNKNOWN"


class MLConfidenceCategory(StrEnum):
    """Mirrors `ml_service.domain.inference.ConfidenceCategory` (Phase 11 brief §36) — an
    explainability aid derived from validation-set thresholds, never called "certainty"."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class StateType(StrEnum):
    """Phase 12 brief §3: the two v1 estimated hidden states, each with its own
    independent Kalman filter and observation channels — never fused into one state
    vector, so Phase 13 can reason over them as distinct evidence sources."""

    LUBRICATION_DELIVERY_STATE = "LUBRICATION_DELIVERY_STATE"
    BEARING_CONDITION_STATE = "BEARING_CONDITION_STATE"


class StateTrend(StrEnum):
    """Derived from the filter's posterior rate-of-change state, not a heuristic guess
    (Phase 12 brief §16). `UNKNOWN` when uncertainty is too high or too few observations
    have been used recently to trust a directional claim."""

    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DETERIORATING = "DETERIORATING"
    UNKNOWN = "UNKNOWN"


class StateUncertaintyCategory(StrEnum):
    """Explainability aid derived from the filter's posterior covariance (Phase 12 brief
    §12) — never confused with fault severity, which this layer does not estimate."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


# ---------------------------------------------------------------------------
# Phase 13 — Condition Intelligence
# ---------------------------------------------------------------------------


class ConditionType(StrEnum):
    """Phase 13 brief §13.4's cautious initial taxonomy — evidence language, never a
    confirmed-fault claim (same causal-language discipline as `RuleFindingType`,
    `docs/FAILURE_MODE_CATALOG.md` §13). Exactly the 12 values the brief lists."""

    NORMAL_OPERATION = "NORMAL_OPERATION"
    LUBRICATION_DELIVERY_DEGRADATION = "LUBRICATION_DELIVERY_DEGRADATION"
    DEVELOPING_RESTRICTION_PATTERN = "DEVELOPING_RESTRICTION_PATTERN"
    DELIVERY_BLOCKAGE_PATTERN = "DELIVERY_BLOCKAGE_PATTERN"
    POSSIBLE_LEAKAGE_PATTERN = "POSSIBLE_LEAKAGE_PATTERN"
    PUMP_PERFORMANCE_DEGRADATION = "PUMP_PERFORMANCE_DEGRADATION"
    LOW_LUBRICANT_AVAILABILITY = "LOW_LUBRICANT_AVAILABILITY"
    BEARING_CONDITION_DEGRADATION = "BEARING_CONDITION_DEGRADATION"
    INDEPENDENT_BEARING_CONDITION = "INDEPENDENT_BEARING_CONDITION"
    SENSOR_OR_DATA_QUALITY_LIMITATION = "SENSOR_OR_DATA_QUALITY_LIMITATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AMBIGUOUS_CONDITION = "AMBIGUOUS_CONDITION"


class ConditionSeverity(StrEnum):
    """Same 4-point scale as `RuleFindingSeverity`, deliberately reused rather than
    reinvented — a `ConditionAssessment` synthesizes `RuleFinding`s that already use this
    scale, and introducing a second incompatible scale at the layer directly above would
    make "why did severity change between the rule finding and the condition" unanswerable
    (Phase 13 brief §13.12 "why do we think this")."""

    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConditionConfidence(StrEnum):
    """Categorical only (Phase 13 brief §13.6) — never a fabricated percentage.
    Deliberately a distinct enum from `MLConfidenceCategory`/`StateUncertaintyCategory`
    even though the values line up, because a condition's confidence is a *synthesis*
    judgment over multiple evidence sources, not a copy of any one source's own
    confidence/uncertainty score."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class ConditionLifecycle(StrEnum):
    """Phase 13 brief §13.11. Deliberately its own vocabulary, not reused from
    `RuleFindingState`'s CANDIDATE/ACTIVE/RECOVERING/RESOLVED — a condition assessment is
    a synthesis judgment re-evaluated on every call, not a debounced detector state
    machine; see `docs/CONDITION_INTELLIGENCE.md` "Condition lifecycle"."""

    DETECTED = "DETECTED"
    DEVELOPING = "DEVELOPING"
    PERSISTENT = "PERSISTENT"
    IMPROVING = "IMPROVING"
    RESOLVED = "RESOLVED"


# ---------------------------------------------------------------------------
# Phase 15 — Prognostics
# ---------------------------------------------------------------------------


class PrognosticStatus(StrEnum):
    """Mirrors `MLInferenceStatus`'s OK/INSUFFICIENT_FEATURES shape (Phase 11) for the
    same reason: a forecast can be genuinely unavailable, and that must be a first-class,
    structured outcome rather than a degenerate/fabricated number (Phase 15 brief §15.7)."""

    OK = "OK"
    NO_RELIABLE_FORECAST = "NO_RELIABLE_FORECAST"


class ForecastHorizon(StrEnum):
    """Phase 15 brief §15.5 — generic horizons appropriate to this system's accelerated
    demo telemetry cadence, never presented as validated production timing."""

    ONE_HOUR = "ONE_HOUR"
    SIX_HOURS = "SIX_HOURS"
    TWENTY_FOUR_HOURS = "TWENTY_FOUR_HOURS"


# ---------------------------------------------------------------------------
# Phase 14 — Decision Intelligence
# ---------------------------------------------------------------------------


class DecisionPriority(StrEnum):
    """Phase 14 brief §14.4."""

    MONITOR = "MONITOR"
    PLANNED = "PLANNED"
    HIGH = "HIGH"
    URGENT = "URGENT"


class RecommendedAction(StrEnum):
    """Phase 14 brief §14.5 — safe, generic actions only; never a physical control
    command (CLAUDE.md "Workflow Intelligence" boundary)."""

    CONTINUE_MONITORING = "CONTINUE_MONITORING"
    VERIFY_SENSOR = "VERIFY_SENSOR"
    INSPECT_LUBRICATION_PATH = "INSPECT_LUBRICATION_PATH"
    INSPECT_DISTRIBUTOR = "INSPECT_DISTRIBUTOR"
    CHECK_RESERVOIR = "CHECK_RESERVOIR"
    CHECK_PUMP = "CHECK_PUMP"
    INSPECT_BEARING = "INSPECT_BEARING"
    SCHEDULE_MAINTENANCE = "SCHEDULE_MAINTENANCE"
    REQUEST_ADDITIONAL_MEASUREMENT = "REQUEST_ADDITIONAL_MEASUREMENT"


class RecommendedWindow(StrEnum):
    """Phase 14 brief §14.6 — explainable scheme, never a fabricated exact service
    interval."""

    NOW = "NOW"
    WITHIN_HOURS = "WITHIN_HOURS"
    NEXT_PLANNED_MAINTENANCE = "NEXT_PLANNED_MAINTENANCE"
    MONITOR = "MONITOR"


class DecisionLifecycle(StrEnum):
    """Phase 14 brief §14.12 — prior decisions are never silently overwritten; a new
    assessment for the same machine supersedes (not deletes) the previous ACTIVE one."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    RESOLVED = "RESOLVED"


# ---------------------------------------------------------------------------
# Phase 16 — Alert Correlation + Incident Management
# ---------------------------------------------------------------------------


class IncidentState(StrEnum):
    """Phase 16 brief §16.6. `DETECTED` is contract-complete (defined for a future
    automated-alert pre-triage stage) but not the state `IncidentService` assigns on
    creation today — see ADR-126: incidents are only ever created from real, confirmed
    fault evidence, so they start at `OPEN`, never a speculative pre-triage state."""

    DETECTED = "DETECTED"
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    ACTION_PLANNED = "ACTION_PLANNED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class IncidentEventType(StrEnum):
    """Phase 16 brief §16.8 — append-only timeline entries; history is never mutated."""

    INCIDENT_CREATED = "INCIDENT_CREATED"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    SEVERITY_CHANGED = "SEVERITY_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATION_STARTED = "INVESTIGATION_STARTED"
    ACTION_PLANNED = "ACTION_PLANNED"
    TECHNICIAN_FINDING_RECORDED = "TECHNICIAN_FINDING_RECORDED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


# ---------------------------------------------------------------------------
# Phase 17 — Maintenance Workflow
# ---------------------------------------------------------------------------


class MaintenanceState(StrEnum):
    """Phase 17 brief §17.2."""

    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_STARTED = "NOT_STARTED"
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_VERIFICATION = "AWAITING_VERIFICATION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TechnicianFindingResult(StrEnum):
    """Phase 17 brief §17.6 — deliberately not a binary confirm/deny; a real technician
    outcome is often partial or points at a different problem entirely (§17.12)."""

    CONFIRMED = "CONFIRMED"
    NOT_CONFIRMED = "NOT_CONFIRMED"
    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
    DIFFERENT_ISSUE_FOUND = "DIFFERENT_ISSUE_FOUND"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


class MaintenanceActionType(StrEnum):
    """Phase 17 brief §17.7 — recording an action taken by a human, never the system
    performing it (CLAUDE.md "Workflow Intelligence" boundary)."""

    INSPECTED = "INSPECTED"
    CLEANED = "CLEANED"
    REFILLED = "REFILLED"
    COMPONENT_REPLACED = "COMPONENT_REPLACED"
    ADJUSTMENT_RECOMMENDED = "ADJUSTMENT_RECOMMENDED"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
    ESCALATED = "ESCALATED"


class FeedbackClassification(StrEnum):
    """Phase 17 brief §17.9 — matches CLAUDE.md's "Maintenance Workflow" vocabulary
    exactly. Recording this must never automatically retrain a model (ADR-131)."""

    TRUE_POSITIVE = "TRUE_POSITIVE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    MISSED_FAILURE = "MISSED_FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Phase 20 — CMMS Adapter
# ---------------------------------------------------------------------------


class CMMSWorkOrderStatus(StrEnum):
    """Phase 20 brief §20.2 — generic states any CMMS work order might carry; the demo
    adapter never auto-advances a work order past `DRAFT` on its own (§20.4 draft-first)."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Phase 18 — Approved-Knowledge RAG Platform
# ---------------------------------------------------------------------------


class DocumentStatus(StrEnum):
    """Phase 18 brief §18.2 — only APPROVED documents ever enter retrieval context;
    DRAFT/REVIEW/RETIRED must never silently do so (structurally enforced by
    `Retriever`'s query, not just convention — see ADR-138)."""

    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class DocumentType(StrEnum):
    """Phase 18 brief §18.3. `SERVICE_CASE` is deliberately its own type — a synthetic
    historical case is evidence of what happened once, never mandatory procedure
    (§18.13, ADR-141)."""

    OPERATING_GUIDE = "OPERATING_GUIDE"
    SERVICE_PROCEDURE = "SERVICE_PROCEDURE"
    TROUBLESHOOTING_GUIDE = "TROUBLESHOOTING_GUIDE"
    COMPONENT_REFERENCE = "COMPONENT_REFERENCE"
    FAULT_CODE_REFERENCE = "FAULT_CODE_REFERENCE"
    SAFETY_NOTE = "SAFETY_NOTE"
    SERVICE_CASE = "SERVICE_CASE"


class RetrievalSufficiency(StrEnum):
    """Phase 18 brief §18.11 — explainable, never a fabricated confidence percentage."""

    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Phase 19 — Guarded GenAI Agent
# ---------------------------------------------------------------------------


class AgentMessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class AgentToolCallStatus(StrEnum):
    """Phase 19 brief §19.10/§19.19 — `DENIED` covers a tool name outside the explicit
    allowlist, failing closed rather than silently ignoring the request."""

    OK = "OK"
    ERROR = "ERROR"
    DENIED = "DENIED"


# ---------------------------------------------------------------------------
# Phase 24 — Security / RBAC
# ---------------------------------------------------------------------------


class UserRole(StrEnum):
    """Phase 24 brief §24.2 — six roles for the demo/reference authorization model. See
    `app.auth.permissions.ROLE_PERMISSIONS` for the exact capability matrix and
    `docs/SECURITY.md` for the rationale behind each grant (ADR-149)."""

    VIEWER = "VIEWER"
    TECHNICIAN = "TECHNICIAN"
    RELIABILITY_ENGINEER = "RELIABILITY_ENGINEER"
    PLANT_MANAGER = "PLANT_MANAGER"
    DATA_SCIENTIST = "DATA_SCIENTIST"
    ADMIN = "ADMIN"


# ---------------------------------------------------------------------------
# Phase 25 — Auditability
# ---------------------------------------------------------------------------


class AuditActorType(StrEnum):
    """Phase 25 brief §25.3 — distinguishes a human-attributed action from a
    system/scheduler-triggered one and from an agent-prepared draft. A `SYSTEM` event
    must never be recorded as if a person performed it."""

    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    AGENT = "AGENT"


# ---------------------------------------------------------------------------
# Phase 22 — Product / North-Star Metrics
# ---------------------------------------------------------------------------


class MetricProvenance(StrEnum):
    """Phase 22 brief §22.4 — every product/business metric value must declare which of
    these it is; the three are never mixed into one number (CLAUDE.md "Customer /
    Business Thinking")."""

    MEASURED_PLATFORM_METRIC = "MEASURED_PLATFORM_METRIC"
    DEMO_ESTIMATE = "DEMO_ESTIMATE"
    CONFIGURED_TARGET = "CONFIGURED_TARGET"


# ---------------------------------------------------------------------------
# Phase 21 — Customer / Business Services
# ---------------------------------------------------------------------------


class CustomerOperationalStatus(StrEnum):
    """Phase 21 brief §21.4 — a deliberately cautious, categorical policy (not an opaque
    numeric score) computed by `app.customer_services`. See `docs/CUSTOMER_SERVICES.md`
    for the exact precedence rules."""

    HEALTHY = "HEALTHY"
    ATTENTION_REQUIRED = "ATTENTION_REQUIRED"
    DEGRADED_VISIBILITY = "DEGRADED_VISIBILITY"
    MAINTENANCE_ACTIVE = "MAINTENANCE_ACTIVE"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Phase 30 — Customer Onboarding / Commissioning
# ---------------------------------------------------------------------------


class CommissioningStatus(StrEnum):
    """Phase 30 brief §30.3 — a demo guided-setup workflow, not real physical device
    discovery (§30.2). `FAILED` is reserved for a genuinely blocking validation issue
    (no instrumentation at all); a non-blocking issue (e.g. no telemetry yet) is
    surfaced in `CommissioningSession.validation_issues` without preventing `READY`."""

    DRAFT = "DRAFT"
    CONFIGURING = "CONFIGURING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CapabilityLevel(StrEnum):
    """Phase 30 brief §30.6 — a cautious, instrumentation-driven capability taxonomy;
    never promises a capability the machine's actual sensors cannot support.
    Deliberately does not require `FLOW` for `DELIVERY_INTELLIGENCE` — the flagship
    reference topology itself lacks a flow sensor (§30.5)."""

    NONE = "NONE"
    BASIC_MONITORING = "BASIC_MONITORING"
    DELIVERY_INTELLIGENCE = "DELIVERY_INTELLIGENCE"
    BEARING_INTELLIGENCE = "BEARING_INTELLIGENCE"
    FULL_INTELLIGENCE = "FULL_INTELLIGENCE"


# ---------------------------------------------------------------------------
# Phase 31 — Firmware / Configuration Management
# ---------------------------------------------------------------------------


class DeviceType(StrEnum):
    GATEWAY = "GATEWAY"
    CONTROLLER = "CONTROLLER"
    SENSOR = "SENSOR"


class CompatibilityStatus(StrEnum):
    """Phase 31 brief §31.5 — a simple generic compatibility model over demo firmware
    version data only; never presented as a real manufacturer specification."""

    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_LIMITATIONS = "SUPPORTED_WITH_LIMITATIONS"
    UNKNOWN = "UNKNOWN"
    INCOMPATIBLE = "INCOMPATIBLE"
