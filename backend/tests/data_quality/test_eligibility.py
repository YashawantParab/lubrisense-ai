from __future__ import annotations

from app.data_quality.services.eligibility import resolve_state, worst_severity
from app.domain.enums import Eligibility, IssueSeverity, QualityState
from tests.data_quality.helpers import make_policy


def test_worst_severity_picks_highest() -> None:
    assert (
        worst_severity([IssueSeverity.INFO, IssueSeverity.ERROR, IssueSeverity.WARNING])
        == IssueSeverity.ERROR
    )


def test_worst_severity_of_empty_list_is_none() -> None:
    assert worst_severity([]) is None


def test_resolve_state_no_issues_is_trusted() -> None:
    policy = make_policy()
    state, eligibility = resolve_state([], policy)
    assert state == QualityState.TRUSTED
    assert eligibility == Eligibility.ELIGIBLE


def test_resolve_state_error_is_unusable() -> None:
    policy = make_policy()
    state, eligibility = resolve_state([IssueSeverity.ERROR], policy)
    assert state == QualityState.UNUSABLE
    assert eligibility == Eligibility.INELIGIBLE


def test_resolve_state_warning_is_usable_with_caution() -> None:
    policy = make_policy()
    state, eligibility = resolve_state([IssueSeverity.INFO, IssueSeverity.WARNING], policy)
    assert state == QualityState.USABLE_WITH_CAUTION
    assert eligibility == Eligibility.ELIGIBLE_WITH_CAUTION
