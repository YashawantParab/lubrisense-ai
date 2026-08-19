"""Pure `decide()` logic tests (Phase 14 brief §14.4-§14.9)."""

from __future__ import annotations

from app.decision_intelligence.config.policy import load_decision_intelligence_policy
from app.decision_intelligence.domain.models import ConditionSnapshot, ProgSnapshot
from app.decision_intelligence.services.decision_synthesis import decide

POLICY = load_decision_intelligence_policy()


def _condition(
    condition_type: str,
    severity: str = "WARNING",
    lifecycle_state: str = "DETECTED",
    confidence: str = "MODERATE",
) -> ConditionSnapshot:
    return ConditionSnapshot(
        id="c-1",
        condition_type=condition_type,
        lifecycle_state=lifecycle_state,
        severity=severity,
        confidence=confidence,
        what_is_happening="test",
    )


def _prog(status: str = "OK", crossing_seconds: float | None = None) -> ProgSnapshot:
    return ProgSnapshot(id="p-1", status=status, threshold_crossing_seconds=crossing_seconds)


def test_normal_operation_is_monitor_continue_monitoring() -> None:
    result = decide(_condition("NORMAL_OPERATION", severity="INFO"), [], "MEDIUM", POLICY)
    assert result.priority == "MONITOR"
    assert result.recommended_action == "CONTINUE_MONITORING"
    assert result.human_review_required is False


def test_insufficient_evidence_requests_additional_measurement_not_maintenance() -> None:
    result = decide(_condition("INSUFFICIENT_EVIDENCE", severity="INFO"), [], "MEDIUM", POLICY)
    assert result.recommended_action == "REQUEST_ADDITIONAL_MEASUREMENT"
    assert result.human_review_required is False


def test_sensor_quality_limitation_requests_sensor_verification() -> None:
    result = decide(
        _condition("SENSOR_OR_DATA_QUALITY_LIMITATION", severity="INFO"), [], "MEDIUM", POLICY
    )
    assert result.recommended_action == "VERIFY_SENSOR"
    assert result.human_review_required is False


def test_fault_pattern_severity_maps_to_base_priority_tier() -> None:
    result = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING"), [], "MEDIUM", POLICY
    )
    assert result.priority == "PLANNED"
    assert result.recommended_action == "INSPECT_LUBRICATION_PATH"
    assert result.human_review_required is True


def test_critical_severity_is_urgent() -> None:
    result = decide(
        _condition("DELIVERY_BLOCKAGE_PATTERN", severity="CRITICAL"), [], "MEDIUM", POLICY
    )
    assert result.priority == "URGENT"
    assert result.recommended_window == "NOW"


def test_persistent_lifecycle_increases_priority() -> None:
    baseline = decide(
        _condition(
            "DEVELOPING_RESTRICTION_PATTERN", severity="WARNING", lifecycle_state="DETECTED"
        ),
        [],
        "MEDIUM",
        POLICY,
    )
    persistent = decide(
        _condition(
            "DEVELOPING_RESTRICTION_PATTERN", severity="WARNING", lifecycle_state="PERSISTENT"
        ),
        [],
        "MEDIUM",
        POLICY,
    )
    assert POLICY.tier_for_priority(persistent.priority) > POLICY.tier_for_priority(
        baseline.priority
    )


def test_high_criticality_increases_priority_only_for_fault_patterns() -> None:
    low_criticality = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING"), [], "LOW", POLICY
    )
    high_criticality = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING"), [], "CRITICAL", POLICY
    )
    assert POLICY.tier_for_priority(high_criticality.priority) > POLICY.tier_for_priority(
        low_criticality.priority
    )


def test_criticality_never_elevates_normal_operation() -> None:
    """Phase 14 brief §14.4: criticality must NOT manufacture evidence that a fault
    exists."""
    result = decide(_condition("NORMAL_OPERATION", severity="INFO"), [], "CRITICAL", POLICY)
    assert result.priority == "MONITOR"
    assert result.recommended_action == "CONTINUE_MONITORING"


def test_criticality_never_elevates_ambiguous_condition() -> None:
    result = decide(_condition("AMBIGUOUS_CONDITION", severity="WARNING"), [], "CRITICAL", POLICY)
    assert result.priority == "PLANNED"
    assert result.recommended_action == "REQUEST_ADDITIONAL_MEASUREMENT"


def test_imminent_threshold_crossing_increases_priority() -> None:
    baseline = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING"), [], "MEDIUM", POLICY
    )
    with_crossing = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING"),
        [_prog(crossing_seconds=1800.0)],
        "MEDIUM",
        POLICY,
    )
    assert POLICY.tier_for_priority(with_crossing.priority) > POLICY.tier_for_priority(
        baseline.priority
    )


def test_far_off_threshold_crossing_does_not_increase_priority() -> None:
    baseline = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING"), [], "MEDIUM", POLICY
    )
    far_crossing = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING"),
        [_prog(crossing_seconds=POLICY.imminent_crossing_seconds * 10)],
        "MEDIUM",
        POLICY,
    )
    assert baseline.priority == far_crossing.priority


def test_priority_is_capped_at_urgent() -> None:
    result = decide(
        _condition("DELIVERY_BLOCKAGE_PATTERN", severity="CRITICAL", lifecycle_state="PERSISTENT"),
        [_prog(crossing_seconds=100.0)],
        "CRITICAL",
        POLICY,
    )
    assert result.priority == "URGENT"


def test_bearing_condition_recommends_bearing_inspection_not_lubrication() -> None:
    """Phase 14 brief: do NOT blame lubrication automatically for a bearing issue."""
    result = decide(
        _condition("INDEPENDENT_BEARING_CONDITION", severity="WARNING"), [], "MEDIUM", POLICY
    )
    assert result.recommended_action == "INSPECT_BEARING"


def test_pump_degradation_recommends_pump_inspection_not_distributor() -> None:
    result = decide(
        _condition("PUMP_PERFORMANCE_DEGRADATION", severity="WARNING"), [], "MEDIUM", POLICY
    )
    assert result.recommended_action == "CHECK_PUMP"


def test_decision_confidence_never_exceeds_condition_confidence() -> None:
    result = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING", confidence="LOW"),
        [],
        "MEDIUM",
        POLICY,
    )
    assert result.confidence == "LOW"


def test_evidence_dict_contains_all_required_explainability_fields() -> None:
    """Phase 14 brief §14.11: what/why/when/risk/confidence/missing-data."""
    result = decide(
        _condition("DEVELOPING_RESTRICTION_PATTERN", severity="WARNING"), [], "MEDIUM", POLICY
    )
    for key in (
        "what_should_i_do",
        "why",
        "when",
        "risk_if_deferred",
        "confidence",
        "missing_data",
    ):
        assert key in result.evidence
