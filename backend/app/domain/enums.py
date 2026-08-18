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
