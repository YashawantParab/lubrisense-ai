"""Lubrication-cycle rules (Phase 9 brief §10 items 3/6/7) — machine-scoped, built from
Phase 8's `CYCLE_METRIC` baseline (`app.baselines.domain.cycle_metrics`) and a freshly
computed recent-window cycle summary using the identical math. Pure functions, no database.
"""

from __future__ import annotations

from app.domain.enums import EvidenceStrength, RuleCategory, RuleFindingType
from app.rules_engine.config.policy import RulesPolicy
from app.rules_engine.domain.context import CycleSignalEvaluation
from app.rules_engine.domain.deviation import evidence_strength_for, is_material
from app.rules_engine.domain.results import RuleFindingCandidate


def check_pressure_build_slow(
    cycle: CycleSignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    if (
        not cycle.eligible
        or cycle.recent_median_rise_time_seconds is None
        or cycle.baseline_median_rise_time_seconds is None
        or cycle.baseline_median_rise_time_seconds <= 0
        or cycle.rise_time_ratio is None
    ):
        return None
    if cycle.rise_time_ratio < policy.cycle.pressure_build_slow_mad_multiplier:
        return None
    strength = (
        EvidenceStrength.STRONG
        if cycle.rise_time_ratio >= policy.cycle.pressure_build_slow_mad_multiplier * 1.5
        else EvidenceStrength.MODERATE
    )
    return RuleFindingCandidate(
        finding_type=RuleFindingType.PRESSURE_BUILD_SLOW,
        rule_id="pressure_build_slow",
        rule_version="1",
        category=RuleCategory.LUBRICATION_CYCLE,
        component_type=cycle.component_type,
        component_id=cycle.component_id,
        evidence_strength=strength,
        message=(
            f"Pressure-build (rise) time is materially slower than baseline "
            f"({cycle.recent_median_rise_time_seconds:.3g}s observed vs. "
            f"{cycle.baseline_median_rise_time_seconds:.3g}s baseline, "
            f"{cycle.rise_time_ratio:.2g}x)."
        ),
        evidence={
            "pressure_rise_time": {
                "observed_seconds": cycle.recent_median_rise_time_seconds,
                "baseline_seconds": cycle.baseline_median_rise_time_seconds,
                "ratio": cycle.rise_time_ratio,
                "cycles_evaluated": cycle.recent_cycle_count,
            }
        },
        limitations=[
            "A ratio against baseline rise time, not a robust standardized distance — the "
            "cycle baseline does not currently track rise-time spread.",
            "Consistent with pump degradation or restriction; does not distinguish them alone.",
        ],
        source_event_ids=list(cycle.source_event_ids),
        baseline_version_ids=[str(cycle.baseline_profile_id)] if cycle.baseline_profile_id else [],
        quality_context={},
    )


def check_cycle_duration_above_baseline(
    cycle: CycleSignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    if (
        not cycle.eligible
        or cycle.duration_deviation_classification is None
        or not is_material(cycle.duration_deviation_classification)
        or cycle.recent_median_duration_seconds is None
        or cycle.baseline_median_duration_seconds is None
        or cycle.recent_median_duration_seconds <= cycle.baseline_median_duration_seconds
    ):
        return None
    strength = evidence_strength_for(
        cycle.duration_deviation_classification,
        caution=False,
        caution_cap=EvidenceStrength[policy.quality.caution_caps_evidence_strength_at],
    )
    return RuleFindingCandidate(
        finding_type=RuleFindingType.CYCLE_DURATION_ABOVE_BASELINE,
        rule_id="cycle_duration_above_baseline",
        rule_version="1",
        category=RuleCategory.LUBRICATION_CYCLE,
        component_type=cycle.component_type,
        component_id=cycle.component_id,
        evidence_strength=strength,
        message=(
            f"Lubrication-cycle duration is materially above baseline "
            f"({cycle.recent_median_duration_seconds:.3g}s observed vs. "
            f"{cycle.baseline_median_duration_seconds:.3g}s baseline)."
        ),
        evidence={
            "cycle_duration": {
                "observed_seconds": cycle.recent_median_duration_seconds,
                "baseline_seconds": cycle.baseline_median_duration_seconds,
                "standardized_distance": cycle.duration_deviation_distance,
                "cycles_evaluated": cycle.recent_cycle_count,
            }
        },
        limitations=[
            "Longer cycles are consistent with several causes; further inspection recommended."
        ],
        source_event_ids=list(cycle.source_event_ids),
        baseline_version_ids=[str(cycle.baseline_profile_id)] if cycle.baseline_profile_id else [],
        quality_context={},
    )


def check_cycle_completion_failure(
    cycle: CycleSignalEvaluation, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    if (
        not cycle.eligible
        or cycle.recent_completion_success_rate is None
        or cycle.recent_cycle_count == 0
    ):
        return None
    failure_rate = 1.0 - cycle.recent_completion_success_rate
    if failure_rate >= policy.cycle.completion_failure_rate_critical:
        strength = EvidenceStrength.STRONG
    elif failure_rate >= policy.cycle.completion_failure_rate_warning:
        strength = EvidenceStrength.MODERATE
    else:
        return None
    return RuleFindingCandidate(
        finding_type=RuleFindingType.CYCLE_COMPLETION_FAILURE,
        rule_id="cycle_completion_failure",
        rule_version="1",
        category=RuleCategory.LUBRICATION_CYCLE,
        component_type=cycle.component_type,
        component_id=cycle.component_id,
        evidence_strength=strength,
        message=(
            f"{failure_rate:.0%} of recent lubrication cycles did not confirm completion "
            f"({cycle.recent_cycle_count} cycles evaluated)."
        ),
        evidence={
            "cycle_completion": {
                "failure_rate": failure_rate,
                "cycles_evaluated": cycle.recent_cycle_count,
                "warning_threshold": policy.cycle.completion_failure_rate_warning,
                "critical_threshold": policy.cycle.completion_failure_rate_critical,
            }
        },
        limitations=["Does not by itself identify which component blocked delivery."],
        source_event_ids=list(cycle.source_event_ids),
        quality_context={},
    )
