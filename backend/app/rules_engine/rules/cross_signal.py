"""Cross-signal pattern rules (Phase 9 brief §12-§15) — the physically-meaningful
combinations that distinguish restriction / leakage / pump degradation from each other and
from an undifferentiated multi-signal deviation. Every pattern is evidence language
("pattern consistent with..."), never a confirmed diagnosis (`docs/FAILURE_MODE_CATALOG.md`
§13's causal-language rules apply identically here).

Pure functions, no database: each takes the set of single-signal/cycle/reservoir
`RuleFindingCandidate`s already produced *this same cycle* (keyed by `RuleFindingType`) plus
`RulesPolicy` — never re-touches telemetry itself. This is why these rules must run *after*
every single-signal/cycle/reservoir check in `app.rules_engine.services.rule_engine`.
"""

from __future__ import annotations

from typing import Any

from app.domain.enums import RuleCategory, RuleFindingType
from app.rules_engine.config.policy import CrossSignalPatternPolicy, RulesPolicy
from app.rules_engine.domain.results import RuleFindingCandidate
from app.rules_engine.domain.strength import escalate_one, weakest

FindingMap = dict[RuleFindingType, RuleFindingCandidate]


def _pattern_evidence(
    required: list[RuleFindingCandidate], supporting: list[RuleFindingCandidate]
) -> dict[str, Any]:
    evidence: dict[str, Any] = {"required_signals": {}, "supporting_signals": {}}
    for f in required:
        evidence["required_signals"][f.finding_type.value] = f.evidence
    for f in supporting:
        evidence["supporting_signals"][f.finding_type.value] = f.evidence
    return evidence


def _evaluate_pattern(
    findings_by_type: FindingMap,
    pattern_policy: CrossSignalPatternPolicy,
) -> tuple[list[RuleFindingCandidate], list[RuleFindingCandidate]] | None:
    """`None` if the pattern's `requires` are not all present, or any `excludes` finding
    *is* present. Otherwise the (required, supporting-present) finding lists."""
    required_types = [RuleFindingType(t) for t in pattern_policy.requires]
    if not required_types or not all(t in findings_by_type for t in required_types):
        return None
    excluded_types = [RuleFindingType(t) for t in pattern_policy.excludes]
    if any(t in findings_by_type for t in excluded_types):
        return None
    required = [findings_by_type[t] for t in required_types]
    supporting_types = [RuleFindingType(t) for t in pattern_policy.supporting]
    supporting = [findings_by_type[t] for t in supporting_types if t in findings_by_type]
    return required, supporting


def check_restriction_pattern(
    findings_by_type: FindingMap, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    matched = _evaluate_pattern(findings_by_type, policy.cross_signal.restriction)
    if matched is None:
        return None
    required, supporting = matched
    strength = weakest([f.evidence_strength for f in required])
    if supporting:
        strength = escalate_one(strength)
    anchor = required[0]
    return RuleFindingCandidate(
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        rule_id="flow_pressure_restriction_pattern",
        rule_version="1",
        category=RuleCategory.CROSS_SIGNAL,
        component_type=anchor.component_type,
        component_id=anchor.component_id,
        evidence_strength=strength,
        message=(
            "Flow below expected together with pressure above expected — pattern is "
            "consistent with a developing delivery-path restriction. Further inspection "
            "recommended to confirm."
        ),
        evidence=_pattern_evidence(required, supporting),
        limitations=[
            "Evidence is consistent with a developing restriction; it does not confirm one.",
            "Does not rule out pump degradation or a sensor-side cause on its own.",
            "On a shared-cycle lubrication system, a fault on one circuit can affect "
            "cycle timing for other circuits sharing the same pump/controller "
            "(docs/SCENARIO_ENGINE.md §7) — component attribution above is the anchoring "
            "signal's own circuit, not a proof the fault originates there exclusively.",
        ],
        source_event_ids=sorted({eid for f in required + supporting for eid in f.source_event_ids}),
        baseline_version_ids=sorted(
            {bid for f in required + supporting for bid in f.baseline_version_ids}
        ),
        quality_context={"corroborating_signals": [f.finding_type.value for f in supporting]},
    )


def check_leakage_pattern(
    findings_by_type: FindingMap, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    matched = _evaluate_pattern(findings_by_type, policy.cross_signal.leakage)
    if matched is None:
        return None
    required, supporting = matched
    strength = weakest([f.evidence_strength for f in required])
    anchor = required[0]
    return RuleFindingCandidate(
        finding_type=RuleFindingType.FLOW_PRESSURE_LEAKAGE_PATTERN,
        rule_id="flow_pressure_leakage_pattern",
        rule_version="1",
        category=RuleCategory.CROSS_SIGNAL,
        component_type=anchor.component_type,
        component_id=anchor.component_id,
        evidence_strength=strength,
        message=(
            "Flow below expected together with reservoir depleting faster than baseline, "
            "without the pressure rise a restriction would show — pattern is consistent "
            "with possible leakage. Further physical inspection recommended to confirm."
        ),
        evidence=_pattern_evidence(required, supporting),
        limitations=[
            "Evidence is consistent with possible leakage; it does not confirm it.",
            "Does not localize where along the delivery path a leak might be.",
            "Faster reservoir depletion has other possible causes (over-lubrication or "
            "increased duty cycle) not ruled out by this pattern alone.",
        ],
        source_event_ids=sorted({eid for f in required for eid in f.source_event_ids}),
        baseline_version_ids=sorted({bid for f in required for bid in f.baseline_version_ids}),
        quality_context={},
    )


def check_pump_degradation_pattern(
    findings_by_type: FindingMap, policy: RulesPolicy
) -> RuleFindingCandidate | None:
    matched = _evaluate_pattern(findings_by_type, policy.cross_signal.pump_degradation)
    if matched is None:
        return None
    required, supporting = matched
    strength = weakest([f.evidence_strength for f in required])
    if supporting:
        strength = escalate_one(strength)
    anchor = required[0]
    return RuleFindingCandidate(
        finding_type=RuleFindingType.PUMP_DEGRADATION_PATTERN,
        rule_id="pump_degradation_pattern",
        rule_version="1",
        category=RuleCategory.CROSS_SIGNAL,
        component_type=anchor.component_type,
        component_id=anchor.component_id,
        evidence_strength=strength,
        message=(
            "Pressure build (rise) time is slower than baseline without the elevated peak "
            "pressure a restriction would show — pattern is consistent with gradual pump "
            "degradation. Further inspection recommended to confirm."
        ),
        evidence=_pattern_evidence(required, supporting),
        limitations=[
            "Evidence is consistent with gradual pump degradation; it does not confirm it.",
            "Relies on pressure-build timing, which is a narrower signal than a full "
            "pump-efficiency measurement — see docs/RULES_ENGINE.md limitations.",
        ],
        source_event_ids=sorted({eid for f in required + supporting for eid in f.source_event_ids}),
        baseline_version_ids=sorted(
            {bid for f in required + supporting for bid in f.baseline_version_ids}
        ),
        quality_context={"corroborating_signals": [f.finding_type.value for f in supporting]},
    )


def check_lubrication_path_degradation_pattern(
    findings_by_type: FindingMap,
    already_matched_specific_pattern: bool,
    policy: RulesPolicy,
) -> RuleFindingCandidate | None:
    """Generic catch-all (brief §15) — deliberately does NOT fire when a more specific
    pattern (restriction/leakage/pump degradation) already matched this cycle, so evidence
    is never double-counted into two findings; only fires when several lubrication-system
    signals are deviating but do not cleanly separate into one of the specific signatures."""
    if already_matched_specific_pattern:
        return None
    lubrication_types = {RuleFindingType(t) for t in policy.bearing.lubrication_signal_types}
    present = [f for t, f in findings_by_type.items() if t in lubrication_types]
    minimum = policy.cross_signal.lubrication_path_degradation.minimum_distinct_signals or 2
    if len(present) < minimum:
        return None
    strength = weakest([f.evidence_strength for f in present])
    anchor = present[0]
    return RuleFindingCandidate(
        finding_type=RuleFindingType.LUBRICATION_PATH_DEGRADATION_PATTERN,
        rule_id="lubrication_path_degradation_pattern",
        rule_version="1",
        category=RuleCategory.CROSS_SIGNAL,
        component_type=anchor.component_type,
        component_id=anchor.component_id,
        evidence_strength=strength,
        message=(
            f"{len(present)} distinct lubrication-system signals are deviating from "
            "baseline without a clean restriction/leakage/pump-degradation signature — "
            "pattern is consistent with a developing lubrication-path issue of "
            "undetermined specific type. Further inspection recommended."
        ),
        evidence={"deviating_signals": {f.finding_type.value: f.evidence for f in present}},
        limitations=[
            "Deliberately non-specific: evidence does not cleanly separate into "
            "restriction, leakage, or pump degradation.",
            "Consistent with an early or ambiguous stage of one of those failure modes; "
            "does not confirm any of them.",
        ],
        source_event_ids=sorted({eid for f in present for eid in f.source_event_ids}),
        baseline_version_ids=sorted({bid for f in present for bid in f.baseline_version_ids}),
        quality_context={"distinct_signal_count": len(present)},
    )
