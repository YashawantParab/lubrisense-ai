"""Single-signal evidence rules (Phase 9 brief §11) — each is an evidence *finding*, never
a diagnosis: `FLOW_BELOW_CONTEXTUAL_BASELINE` means "flow is materially below its expected
contextual baseline", not "restriction confirmed". Pure functions, no database — every rule
takes a `SignalEvaluation`/`ReservoirSignalEvaluation` (already quality-gated and
baseline-resolved by `app.rules_engine.services.rule_engine`) plus `RulesPolicy`.
"""

from __future__ import annotations

from app.domain.enums import (
    DeviationClassification,
    EvidenceStrength,
    RuleCategory,
    RuleFindingType,
)
from app.rules_engine.config.policy import RulesPolicy
from app.rules_engine.domain.context import ReservoirSignalEvaluation, SignalEvaluation
from app.rules_engine.domain.deviation import (
    classify_distance,
    evidence_strength_for,
)
from app.rules_engine.domain.results import RuleFindingCandidate

_MODERATE_OR_STRONG = (
    DeviationClassification.MILD_DEVIATION,
    DeviationClassification.STRONG_DEVIATION,
)


def _evidence_strength(
    classification: DeviationClassification, *, caution: bool, policy: RulesPolicy
) -> EvidenceStrength:
    return evidence_strength_for(
        classification,
        caution=caution,
        caution_cap=EvidenceStrength[policy.quality.caution_caps_evidence_strength_at],
    )


def _directional_finding(
    signal: SignalEvaluation,
    *,
    direction: str,
    finding_type: RuleFindingType,
    rule_id: str,
    category: RuleCategory,
    policy: RulesPolicy,
    phrase: str,
) -> RuleFindingCandidate | None:
    """`direction` is `"above"` or `"below"` — the finding only fires if the deviation is
    both material (MILD/STRONG, not WITHIN_EXPECTED_RANGE) *and* points the requested way;
    a strong deviation in the *opposite* direction is not this finding (brief §11's
    single-signal rules are directional, not "any deviation")."""
    if (
        not signal.eligible
        or signal.deviation_classification is None
        or signal.deviation_classification not in _MODERATE_OR_STRONG
        or signal.latest_value is None
        or signal.baseline_median is None
    ):
        return None
    actual_direction = "above" if signal.latest_value > signal.baseline_median else "below"
    if actual_direction != direction:
        return None

    strength = _evidence_strength(
        signal.deviation_classification, caution=signal.caution, policy=policy
    )
    return RuleFindingCandidate(
        finding_type=finding_type,
        rule_id=rule_id,
        rule_version="1",
        category=category,
        component_type=signal.component_type,
        component_id=signal.component_id,
        evidence_strength=strength,
        message=(
            f"{phrase} (observed {signal.latest_value:.3g}, baseline median "
            f"{signal.baseline_median:.3g}, standardized distance "
            f"{signal.deviation_distance:.2g})."
        ),
        evidence={
            signal.measurement_type.lower(): {
                "observed": signal.latest_value,
                "baseline_median": signal.baseline_median,
                "standardized_distance": signal.deviation_distance,
                "classification": signal.deviation_classification.value,
                "sample_count_in_window": signal.sample_count_in_window,
            },
        },
        limitations=[
            "This is a single-signal deviation from baseline, not a fault diagnosis.",
            "Does not by itself indicate which lubrication-system component is responsible.",
        ],
        source_event_ids=[str(signal.latest_event_id)] if signal.latest_event_id else [],
        baseline_version_ids=[str(signal.baseline_profile_id)]
        if signal.baseline_profile_id
        else [],
        quality_context={"caution": signal.caution},
    )


def check_flow_below_contextual_baseline(
    signal: SignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    return _directional_finding(
        signal,
        direction="below",
        finding_type=RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE,
        rule_id="flow_below_contextual_baseline",
        category=RuleCategory.HYDRAULIC,
        policy=policy,
        phrase="Flow is materially below its expected contextual baseline",
    )


def check_pressure_above_contextual_baseline(
    signal: SignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    return _directional_finding(
        signal,
        direction="above",
        finding_type=RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE,
        rule_id="pressure_above_contextual_baseline",
        category=RuleCategory.HYDRAULIC,
        policy=policy,
        phrase="Pressure is materially above its expected contextual baseline",
    )


def check_pump_current_above_baseline(
    signal: SignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    return _directional_finding(
        signal,
        direction="above",
        finding_type=RuleFindingType.PUMP_CURRENT_ABOVE_BASELINE,
        rule_id="pump_current_above_baseline",
        category=RuleCategory.PUMP,
        policy=policy,
        phrase="Pump current is materially above its expected baseline",
    )


def check_pump_runtime_above_baseline(
    signal: SignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    return _directional_finding(
        signal,
        direction="above",
        finding_type=RuleFindingType.PUMP_RUNTIME_ABOVE_BASELINE,
        rule_id="pump_runtime_above_baseline",
        category=RuleCategory.PUMP,
        policy=policy,
        phrase="Pump runtime per cycle is materially above its expected baseline",
    )


def check_bearing_temperature_above_contextual_baseline(
    signal: SignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    return _directional_finding(
        signal,
        direction="above",
        finding_type=RuleFindingType.BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE,
        rule_id="bearing_temperature_above_contextual_baseline",
        category=RuleCategory.BEARING_CONDITION,
        policy=policy,
        phrase="Bearing temperature is materially above its expected contextual baseline",
    )


def check_vibration_above_contextual_baseline(
    signal: SignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    return _directional_finding(
        signal,
        direction="above",
        finding_type=RuleFindingType.VIBRATION_ABOVE_CONTEXTUAL_BASELINE,
        rule_id="vibration_above_contextual_baseline",
        category=RuleCategory.BEARING_CONDITION,
        policy=policy,
        phrase="Vibration is materially above its expected contextual baseline",
    )


def check_reservoir_level_low(
    reservoir: ReservoirSignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    """Engineering-limit-based, not baseline-based (`docs/FAILURE_MODE_CATALOG.md` §7 "Low
    Reservoir") — a reservoir is low relative to a configured physical minimum, not
    relative to its own learned history."""
    if not reservoir.eligible or reservoir.latest_level_percent is None:
        return None
    level = reservoir.latest_level_percent
    if level <= policy.reservoir.low_level_critical_percent:
        strength, label = EvidenceStrength.STRONG, "critically low"
    elif level <= policy.reservoir.low_level_warning_percent:
        strength, label = EvidenceStrength.MODERATE, "low"
    else:
        return None
    return RuleFindingCandidate(
        finding_type=RuleFindingType.RESERVOIR_LEVEL_LOW,
        rule_id="reservoir_level_low",
        rule_version="1",
        category=RuleCategory.RESERVOIR,
        component_type=reservoir.component_type,
        component_id=reservoir.component_id,
        evidence_strength=strength,
        message=(
            f"Reservoir level is {label} ({level:.1f}%, configured warning threshold "
            f"{policy.reservoir.low_level_warning_percent:.1f}%, critical threshold "
            f"{policy.reservoir.low_level_critical_percent:.1f}%)."
        ),
        evidence={
            "reservoir_level": {
                "observed_percent": level,
                "warning_threshold_percent": policy.reservoir.low_level_warning_percent,
                "critical_threshold_percent": policy.reservoir.low_level_critical_percent,
            }
        },
        limitations=[
            "Reflects the configured demo minimum level, not a validated engineering limit.",
            "Does not by itself indicate the cause of depletion (normal consumption vs. leakage).",
        ],
        quality_context={},
    )


def check_reservoir_depletion_abnormal(
    reservoir: ReservoirSignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    if (
        not reservoir.eligible
        or reservoir.recent_depletion_rate_percent_per_hour is None
        or reservoir.baseline_depletion_rate_percent_per_hour is None
        or reservoir.deviation_classification is None
        or reservoir.deviation_classification not in _MODERATE_OR_STRONG
    ):
        return None
    # Depletion-rate-abnormal is one-directional by physical definition: faster depletion
    # only (a *slower* rate is never itself abnormal evidence for this finding).
    if (
        reservoir.recent_depletion_rate_percent_per_hour
        <= reservoir.baseline_depletion_rate_percent_per_hour
    ):
        return None
    strength = _evidence_strength(reservoir.deviation_classification, caution=False, policy=policy)
    return RuleFindingCandidate(
        finding_type=RuleFindingType.RESERVOIR_DEPLETION_ABNORMAL,
        rule_id="reservoir_depletion_abnormal",
        rule_version="1",
        category=RuleCategory.RESERVOIR,
        component_type=reservoir.component_type,
        component_id=reservoir.component_id,
        evidence_strength=strength,
        message=(
            f"Reservoir is depleting faster than its expected baseline rate "
            f"({reservoir.recent_depletion_rate_percent_per_hour:.3g}%/h observed vs. "
            f"{reservoir.baseline_depletion_rate_percent_per_hour:.3g}%/h baseline)."
        ),
        evidence={
            "reservoir_depletion": {
                "observed_rate_percent_per_hour": reservoir.recent_depletion_rate_percent_per_hour,
                "baseline_rate_percent_per_hour": (
                    reservoir.baseline_depletion_rate_percent_per_hour
                ),
                "standardized_distance": reservoir.deviation_distance,
            }
        },
        limitations=[
            "Faster-than-expected depletion is consistent with several causes (leakage, "
            "over-lubrication, increased duty cycle) — further inspection recommended.",
            "Does not distinguish leakage from legitimately increased consumption on its own.",
        ],
        baseline_version_ids=(
            [str(reservoir.baseline_profile_id)] if reservoir.baseline_profile_id else []
        ),
        quality_context={},
    )


def classify_reservoir_trend_deviation(
    recent_rate: float, baseline_rate: float, baseline_mad: float, policy: RulesPolicy
) -> tuple[DeviationClassification, float]:
    """Shared helper `app.rules_engine.services.rule_engine` uses to populate
    `ReservoirSignalEvaluation.deviation_classification` before calling the check above —
    kept here (not in `services/`) so it stays a pure, independently-testable function next
    to the rule it feeds, matching `app.baselines.domain.anchor`'s own placement next to
    `app.baselines.services.promotion`."""
    if baseline_mad <= 0:
        # A large finite sentinel, not `float("inf")` — `inf` is not valid JSON and this
        # value is persisted directly into `RuleFinding.evidence` (JSONB), matching the
        # same fix `app.baselines.domain.deviation.compute_deviation` already applies for
        # its own degenerate-constant case.
        distance = 0.0 if recent_rate == baseline_rate else 1e9
    else:
        distance = abs(recent_rate - baseline_rate) / baseline_mad
    return classify_distance(
        distance,
        mild_multiplier=policy.deviation.mild_multiplier,
        strong_multiplier=policy.deviation.strong_multiplier,
    ), distance
