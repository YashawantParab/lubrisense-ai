"""Deterministic lubrication-energy attribution policy — pure functions, no I/O, no
database (mirrors `app.condition_intelligence.services.synthesis`'s own "pure logic
separate from orchestration" split). Lubrication Efficiency Intelligence, Pass 2
(docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §6, ADR-176).

**Core principle**: an observed energy deviation (Pass 1's `EnergyAssessment`) is
NECESSARY for attribution but never SUFFICIENT — attribution requires independent
evidence from at least one of the lubrication-delivery or bearing/friction-response
families below. No numeric causal percentage is ever produced.

**Evidence-independence / deduplication strategy** — the load-bearing design decision of
this module, because the same underlying physical observation can otherwise be counted
more than once through several derived objects:

- `RuleFinding` rows are grouped into exactly two evidence families
  (`LUBRICATION_DELIVERY`, `BEARING_FRICTION`) by finding_type. Multiple ACTIVE findings
  within the same family (e.g. both `BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE` and
  `VIBRATION_ABOVE_CONTEXTUAL_BASELINE`) count as ONE family vote, not two — they are the
  same physical phenomenon observed through different sensors.
- A `StateEstimate` deteriorating in the same physical domain (`LUBRICATION_DELIVERY_
  STATE`/`BEARING_CONDITION_STATE`) is folded into that SAME family, not counted as a
  third, separate family — `docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md`'s own family C
  definition explicitly groups "relevant state-estimation outputs" under bearing/friction
  response, and it is Kalman-filtered from overlapping underlying telemetry regardless.
- The synthesized `ConditionAssessment` (family D) is deliberately **not** counted as a
  third independent family toward `MODERATE`/`STRONG` — `ConditionEngine.assess()` itself
  derives that condition from the same `RuleFinding`/`StateEstimate` rows this module
  already reads directly, so adding it as a fourth additive vote would double-count the
  identical underlying evidence a second time. Instead it acts as a **gate and
  confirmation signal**: an affirmatively lubrication-family condition raises confidence
  toward `STRONG` (real corroboration from independent computation: rule thresholds AND
  full evidence synthesis agree), and — critically — a condition that explicitly
  contradicts lubrication involvement (`INDEPENDENT_BEARING_CONDITION`, a real,
  already-computed cross-signal rule pattern that only fires when lubrication-delivery
  signals are confirmed within their expected range; or `NORMAL_OPERATION`) hard-caps the
  result at `POSSIBLE` regardless of how many raw families support it. This is the
  mechanism behind CLAUDE.md's own "never claim direct causality from simple
  correlation" applied to this specific product question.
- ML evidence (family G) is never counted toward the family total, matching
  `ConditionEngine._evidence_from_ml_result`'s own EXPERIMENTAL-strength precedent: an
  EXPERIMENT-lifecycle model's prediction is recorded and shown, explicitly labeled
  non-authoritative, but structurally incapable of raising the attribution level on its
  own. The governed STAGING baseline classifier that `ConditionEngine` itself excludes
  from live condition fusion (see `condition_engine.py`'s own comment, and ADR from the
  ML decision-integration pass) is not silently reintroduced here either — only the same
  two models `ConditionEngine` actually reads are ever considered.

**Non-circularity**: this module's output is never read back into
`ConditionEngine`/`DecisionEngine` in this pass — see
`app.energy.services.attribution_service`'s own docstring for where that boundary is
enforced at the orchestration layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import AttributionLevel, BaselineSourceKind, EnergyAssessmentStatus

POLICY_VERSION = "1"

#: `RuleFindingType` values concerning lubrication delivery (pressure, flow, reservoir,
#: pump, cycle, and the cross-signal restriction/leakage/pump-degradation/path-
#: degradation patterns) — family B.
_DELIVERY_FINDING_TYPES = frozenset(
    {
        "FLOW_BELOW_CONTEXTUAL_BASELINE",
        "PRESSURE_ABOVE_CONTEXTUAL_BASELINE",
        "PRESSURE_BUILD_SLOW",
        "PUMP_CURRENT_ABOVE_BASELINE",
        "PUMP_RUNTIME_ABOVE_BASELINE",
        "CYCLE_DURATION_ABOVE_BASELINE",
        "CYCLE_COMPLETION_FAILURE",
        "RESERVOIR_LEVEL_LOW",
        "RESERVOIR_DEPLETION_ABNORMAL",
        "FLOW_PRESSURE_RESTRICTION_PATTERN",
        "FLOW_PRESSURE_LEAKAGE_PATTERN",
        "PUMP_DEGRADATION_PATTERN",
        "LUBRICATION_PATH_DEGRADATION_PATTERN",
    }
)

#: Single-signal bearing/friction `RuleFindingType` values — family C. Deliberately
#: excludes `INDEPENDENT_BEARING_CONDITION_PATTERN`, the cross-signal STRONG finding that
#: maps 1:1 to the contradicting `INDEPENDENT_BEARING_CONDITION` condition_type — that one
#: belongs to the family-D gate below, not this raw family (it IS the synthesis-level
#: verdict, not an independent single-signal observation).
_FRICTION_FINDING_TYPES = frozenset(
    {
        "BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE",
        "VIBRATION_ABOVE_CONTEXTUAL_BASELINE",
    }
)

#: `ConditionType` values genuinely lubrication-linked (family D, supporting).
_LUBRICATION_CONDITION_TYPES = frozenset(
    {
        "LUBRICATION_DELIVERY_DEGRADATION",
        "DEVELOPING_RESTRICTION_PATTERN",
        "DELIVERY_BLOCKAGE_PATTERN",
        "POSSIBLE_LEAKAGE_PATTERN",
        "PUMP_PERFORMANCE_DEGRADATION",
        "LOW_LUBRICANT_AVAILABILITY",
        "BEARING_CONDITION_DEGRADATION",
    }
)

#: `ConditionType` values that actively contradict a lubrication explanation (family D,
#: hard cap at POSSIBLE).
_CONTRADICTING_CONDITION_TYPES = frozenset({"INDEPENDENT_BEARING_CONDITION", "NORMAL_OPERATION"})

#: `ConditionType` values that neither support nor contradict — recorded as a limiting
#: factor, never a vote either way.
_LIMITING_CONDITION_TYPES = frozenset(
    {"SENSOR_OR_DATA_QUALITY_LIMITATION", "INSUFFICIENT_EVIDENCE", "AMBIGUOUS_CONDITION"}
)

_LEVEL_ORDER = (
    AttributionLevel.NO_EVIDENCE,
    AttributionLevel.POSSIBLE,
    AttributionLevel.MODERATE,
    AttributionLevel.STRONG,
)


def _humanize(value: str | None) -> str:
    if value is None:
        return "unknown"
    return value.replace("_", " ").lower()


def _cap(level: AttributionLevel, maximum: AttributionLevel) -> AttributionLevel:
    if _LEVEL_ORDER.index(level) > _LEVEL_ORDER.index(maximum):
        return maximum
    return level


@dataclass(frozen=True)
class RuleFindingSignal:
    """The minimal real fields this policy needs from one `RuleFinding` row — never the
    full ORM row, matching `app.baselines.domain.context.TelemetrySample`'s own
    "plain-data snapshot" convention."""

    finding_type: str
    state: str  # RuleFindingState value; only "ACTIVE" ever votes here


@dataclass(frozen=True)
class StateEstimateSignal:
    state_type: str  # "LUBRICATION_DELIVERY_STATE" | "BEARING_CONDITION_STATE"
    trend: str  # StateTrend value
    uncertainty: str  # StateUncertaintyCategory value
    meaningfully_elevated: bool  # |state_value| >= policy.state_estimate.minimum_meaningful_level


@dataclass(frozen=True)
class MLSignal:
    """One real `MLInferenceResult`, pre-resolved against the live registry (governance
    check happens in the service layer, exactly where `ConditionEngine` already does it
    — this module only renders what it's told, never re-derives lifecycle itself)."""

    model_id: str
    predicted_class: str | None
    anomalous: bool | None
    is_experimental: bool
    condition_hint: str | None


@dataclass(frozen=True)
class AttributionContext:
    energy_status: EnergyAssessmentStatus
    energy_data_quality: str  # QualityState value, power sensor only
    residual_kw: float | None
    residual_pct: float | None
    baseline_source: BaselineSourceKind
    rule_findings: tuple[RuleFindingSignal, ...] = ()
    state_estimates: tuple[StateEstimateSignal, ...] = ()
    condition_type: str | None = None
    condition_data_trustworthiness: str | None = None  # TRUSTED/CAUTION/NO_TRUSTED_DATA/UNTRUSTED
    ml_signals: tuple[MLSignal, ...] = ()


@dataclass(frozen=True)
class AttributionResult:
    level: AttributionLevel
    supporting_evidence: tuple[str, ...] = field(default_factory=tuple)
    contradicting_evidence: tuple[str, ...] = field(default_factory=tuple)
    limiting_factors: tuple[str, ...] = field(default_factory=tuple)
    alternative_explanations: tuple[str, ...] = field(default_factory=tuple)
    data_quality_state: str = "TRUSTED"
    policy_version: str = POLICY_VERSION


def _combine_quality(energy_quality: str, condition_trust: str | None) -> str:
    """Worse-of rollup, reusing `ConditionEngine._overall_quality_state`'s own real
    vocabulary (TRUSTED/CAUTION/NO_TRUSTED_DATA) as the common scale — the coarser one,
    since this attribution spans more than one sensor family."""
    energy_as_condition_scale = {
        "TRUSTED": "TRUSTED",
        "USABLE_WITH_CAUTION": "CAUTION",
        "UNUSABLE": "NO_TRUSTED_DATA",
    }.get(energy_quality, "NO_TRUSTED_DATA")
    rank = {"TRUSTED": 0, "CAUTION": 1, "NO_TRUSTED_DATA": 2, "UNTRUSTED": 2}
    condition_scale = condition_trust or "TRUSTED"
    worse = max((energy_as_condition_scale, condition_scale), key=lambda v: rank.get(v, 2))
    return worse


def derive_attribution(ctx: AttributionContext) -> AttributionResult:
    supporting: list[str] = []
    contradicting: list[str] = []
    limiting: list[str] = []
    alternatives: list[str] = []

    data_quality_state = _combine_quality(
        ctx.energy_data_quality, ctx.condition_data_trustworthiness
    )

    # --- Gate 0: energy deviation is necessary, never sufficient -------------------
    if ctx.energy_status in (
        EnergyAssessmentStatus.INSUFFICIENT_DATA,
        EnergyAssessmentStatus.INSUFFICIENT_BASELINE,
        EnergyAssessmentStatus.DATA_QUALITY_LIMITED,
    ):
        limiting.append(
            "Energy assessment is not yet available or trustworthy for this machine — "
            "there is no resolved residual to attribute."
        )
    elif ctx.energy_status == EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE:
        limiting.append("No elevated energy demand is currently observed — nothing to attribute.")
    elif ctx.energy_status == EnergyAssessmentStatus.BELOW_EXPECTED_RANGE:
        limiting.append(
            "Energy demand is below contextual expectation, not elevated — not a candidate "
            "for friction-related attribution."
        )

    # Independent lubrication/bearing evidence-quality signal is real regardless of
    # whether an energy deviation exists — surfaced even in the NO_EVIDENCE case (e.g.
    # AF-101: no current deviation, but its bearing instrumentation is independently
    # known-degraded, which would constrain any future elevated reading).
    if ctx.condition_data_trustworthiness not in (None, "TRUSTED"):
        limiting.append(
            f"Lubrication/bearing sensor data quality for this machine is currently "
            f"{_humanize(ctx.condition_data_trustworthiness)}."
        )

    if ctx.energy_status != EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND:
        return AttributionResult(
            level=AttributionLevel.NO_EVIDENCE,
            supporting_evidence=tuple(supporting),
            contradicting_evidence=tuple(contradicting),
            limiting_factors=tuple(limiting),
            alternative_explanations=tuple(alternatives),
            data_quality_state=data_quality_state,
        )

    magnitude = (
        f"{ctx.residual_pct:+.1f}%"
        if ctx.residual_pct is not None
        else f"{ctx.residual_kw:+.2f} kW"
    )
    supporting.append(f"Machine power is {magnitude} above its contextual expected range.")

    families_supporting: set[str] = set()

    # --- Family B: lubrication delivery --------------------------------------------
    active_delivery = [
        f
        for f in ctx.rule_findings
        if f.finding_type in _DELIVERY_FINDING_TYPES and f.state == "ACTIVE"
    ]
    delivery_state = next(
        (
            s
            for s in ctx.state_estimates
            if s.state_type == "LUBRICATION_DELIVERY_STATE"
            and s.trend == "DETERIORATING"
            and s.meaningfully_elevated
            and s.uncertainty != "HIGH"
        ),
        None,
    )
    if active_delivery or delivery_state:
        families_supporting.add("LUBRICATION_DELIVERY")
        if active_delivery:
            kinds = ", ".join(sorted({_humanize(f.finding_type) for f in active_delivery}))
            supporting.append(f"Lubrication-delivery evidence active: {kinds}.")
        if delivery_state:
            supporting.append("Lubrication-delivery state estimate is deteriorating.")

    # --- Family C: bearing / friction response --------------------------------------
    active_friction = [
        f
        for f in ctx.rule_findings
        if f.finding_type in _FRICTION_FINDING_TYPES and f.state == "ACTIVE"
    ]
    bearing_state = next(
        (
            s
            for s in ctx.state_estimates
            if s.state_type == "BEARING_CONDITION_STATE"
            and s.trend == "DETERIORATING"
            and s.meaningfully_elevated
            and s.uncertainty != "HIGH"
        ),
        None,
    )
    if active_friction or bearing_state:
        families_supporting.add("BEARING_FRICTION")
        if active_friction:
            kinds = ", ".join(sorted({_humanize(f.finding_type) for f in active_friction}))
            supporting.append(f"Bearing-condition evidence active: {kinds}.")
        if bearing_state:
            supporting.append("Bearing-condition state estimate is deteriorating.")

    # --- Family D: condition intelligence — gate + confirmation, never additive ----
    condition_supports = False
    condition_contradicts = False
    if ctx.condition_type in _LUBRICATION_CONDITION_TYPES:
        condition_supports = True
        supporting.append(
            f"Current synthesized condition ({_humanize(ctx.condition_type)}) is consistent "
            "with lubrication-related deterioration."
        )
    elif ctx.condition_type in _CONTRADICTING_CONDITION_TYPES:
        condition_contradicts = True
        if ctx.condition_type == "INDEPENDENT_BEARING_CONDITION":
            contradicting.append(
                "Current condition assessment attributes this bearing deterioration to an "
                "independent, non-lubrication mechanical cause — lubrication-delivery signals "
                "were confirmed within their expected range."
            )
        else:
            contradicting.append(
                "Current condition assessment finds no active issue on this machine."
            )
    elif ctx.condition_type in _LIMITING_CONDITION_TYPES:
        limiting.append(
            f"Current condition is {_humanize(ctx.condition_type)} — an insufficient/ambiguous "
            "basis to corroborate or rule out lubrication involvement."
        )
    elif ctx.condition_type is None:
        limiting.append("No condition assessment is currently available for this machine.")

    # --- Family G: ML — informational only, never additive -------------------------
    for ml in ctx.ml_signals:
        relevant = (ml.condition_hint in _LUBRICATION_CONDITION_TYPES) or (ml.anomalous is True)
        if not relevant:
            continue
        label = "Experimental" if ml.is_experimental else "Governed"
        detail = (
            f"predicted {_humanize(ml.predicted_class)}"
            if ml.predicted_class
            else "anomaly detected"
        )
        authority = (
            "experimental supporting evidence, not decision-authoritative"
            if ml.is_experimental
            else "governed supporting evidence"
        )
        supporting.append(f"{label} ML evidence ({ml.model_id}): {detail} — {authority}.")

    # --- Family F: operating context / alternative explanations --------------------
    if ctx.baseline_source == BaselineSourceKind.EXACT_CONTEXT:
        alternatives.append(
            "Process-load/operating-mode change is controlled by the contextual expected-power "
            "baseline (matched to the exact current operating context)."
        )
    else:
        limiting.append(
            f"Expected-power baseline resolved from a coarser fallback "
            f"({_humanize(ctx.baseline_source.value)}) than an exact operating-context match — "
            "load/mode effects are less tightly controlled than usual."
        )
    alternatives.append(
        "Other mechanical causes independent of lubrication cannot be fully excluded from the "
        "evidence available."
    )
    alternatives.append(
        "This assessment is evaluated on synthetic industrial scenarios and demonstrates "
        "evidence-fusion architecture, not validated field causality."
    )

    # --- Family E: data trust caps -------------------------------------------------
    quality_capped = data_quality_state != "TRUSTED"
    if ctx.energy_data_quality != "TRUSTED":
        limiting.append(
            f"Machine-power sensor data quality is {_humanize(ctx.energy_data_quality)}."
        )

    # --- Decision --------------------------------------------------------------------
    n_families = len(families_supporting)
    if n_families == 0:
        level = AttributionLevel.NO_EVIDENCE
    elif condition_contradicts or n_families == 1:
        # Two distinct real reasons landing on the same result: a contradicting
        # condition caps confidence regardless of family count, and a single
        # independent family (with no contradiction) is exactly "possible, not yet
        # corroborated" — neither reaches MODERATE/STRONG.
        level = AttributionLevel.POSSIBLE
    else:
        strong_candidate = (
            condition_supports
            and ctx.baseline_source == BaselineSourceKind.EXACT_CONTEXT
            and not quality_capped
            and bool(active_delivery or active_friction)
        )
        level = AttributionLevel.STRONG if strong_candidate else AttributionLevel.MODERATE

    if quality_capped:
        level = _cap(level, AttributionLevel.POSSIBLE)

    return AttributionResult(
        level=level,
        supporting_evidence=tuple(supporting),
        contradicting_evidence=tuple(contradicting),
        limiting_factors=tuple(limiting),
        alternative_explanations=tuple(alternatives),
        data_quality_state=data_quality_state,
    )
