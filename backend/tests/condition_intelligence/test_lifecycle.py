"""Pure `classify_lifecycle()` tests (Phase 13 brief §13.11)."""

from __future__ import annotations

from app.condition_intelligence.config.policy import load_condition_intelligence_policy
from app.condition_intelligence.services.lifecycle import RecentAssessment, classify_lifecycle

POLICY = load_condition_intelligence_policy()


def test_no_history_is_detected() -> None:
    result = classify_lifecycle([], "DEVELOPING_RESTRICTION_PATTERN", "WARNING", POLICY)
    assert result.lifecycle_state == "DETECTED"
    assert result.inherit_first_detected_at is False


def test_new_type_different_from_prior_is_detected() -> None:
    recent = [RecentAssessment("NORMAL_OPERATION", "INFO")]
    result = classify_lifecycle(recent, "DEVELOPING_RESTRICTION_PATTERN", "WARNING", POLICY)
    assert result.lifecycle_state == "DETECTED"
    assert result.inherit_first_detected_at is False


def test_transition_to_normal_from_a_fault_is_resolved() -> None:
    recent = [RecentAssessment("DEVELOPING_RESTRICTION_PATTERN", "WARNING")]
    result = classify_lifecycle(recent, "NORMAL_OPERATION", "INFO", POLICY)
    assert result.lifecycle_state == "RESOLVED"


def test_normal_to_normal_stays_detected() -> None:
    recent = [RecentAssessment("NORMAL_OPERATION", "INFO")]
    result = classify_lifecycle(recent, "NORMAL_OPERATION", "INFO", POLICY)
    assert result.lifecycle_state == "DETECTED"


def test_second_consecutive_same_type_is_developing() -> None:
    recent = [RecentAssessment("DEVELOPING_RESTRICTION_PATTERN", "WARNING")]
    result = classify_lifecycle(recent, "DEVELOPING_RESTRICTION_PATTERN", "WARNING", POLICY)
    assert result.lifecycle_state == "DEVELOPING"
    assert result.inherit_first_detected_at is True


def test_third_consecutive_same_type_is_persistent() -> None:
    recent = [
        RecentAssessment("DEVELOPING_RESTRICTION_PATTERN", "WARNING"),
        RecentAssessment("DEVELOPING_RESTRICTION_PATTERN", "WARNING"),
    ]
    result = classify_lifecycle(recent, "DEVELOPING_RESTRICTION_PATTERN", "WARNING", POLICY)
    assert result.lifecycle_state == "PERSISTENT"


def test_severity_decrease_on_same_type_is_improving() -> None:
    recent = [
        RecentAssessment("DEVELOPING_RESTRICTION_PATTERN", "CRITICAL"),
        RecentAssessment("DEVELOPING_RESTRICTION_PATTERN", "CRITICAL"),
    ]
    result = classify_lifecycle(recent, "DEVELOPING_RESTRICTION_PATTERN", "WARNING", POLICY)
    assert result.lifecycle_state == "IMPROVING"


def test_severity_increase_does_not_count_as_improving() -> None:
    recent = [RecentAssessment("DEVELOPING_RESTRICTION_PATTERN", "WARNING")]
    result = classify_lifecycle(recent, "DEVELOPING_RESTRICTION_PATTERN", "CRITICAL", POLICY)
    assert result.lifecycle_state == "DEVELOPING"


def test_non_consecutive_run_resets_the_consecutive_count() -> None:
    """A same-type row that is NOT the immediately preceding one does not count toward
    consecutive-run length — only an unbroken run does."""
    recent = [
        RecentAssessment("NORMAL_OPERATION", "INFO"),
        RecentAssessment("DEVELOPING_RESTRICTION_PATTERN", "WARNING"),
    ]
    result = classify_lifecycle(recent, "DEVELOPING_RESTRICTION_PATTERN", "WARNING", POLICY)
    # prior (recent[0]) is NORMAL_OPERATION, different type -> DETECTED, not DEVELOPING
    assert result.lifecycle_state == "DETECTED"
