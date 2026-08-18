"""Unit tests for `app.rules_engine.services.lifecycle.decide` — the pure debounce/
hysteresis state machine, no database (Phase 9 brief §19/§20/§29)."""

from __future__ import annotations

from app.domain.enums import RuleFindingState
from app.rules_engine.services.lifecycle import LifecycleAction, decide


def test_first_fire_creates_candidate() -> None:
    decision = decide(
        row_exists=False,
        row_state=None,
        row_candidate_stable_cycles=0,
        fired=True,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.CREATE_CANDIDATE
    assert decision.candidate_stable_cycles == 1


def test_candidate_advances_while_below_threshold() -> None:
    decision = decide(
        row_exists=True,
        row_state=RuleFindingState.CANDIDATE,
        row_candidate_stable_cycles=1,
        fired=True,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.ADVANCE_CANDIDATE
    assert decision.candidate_stable_cycles == 2


def test_candidate_activates_once_threshold_reached() -> None:
    decision = decide(
        row_exists=True,
        row_state=RuleFindingState.CANDIDATE,
        row_candidate_stable_cycles=2,
        fired=True,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.ACTIVATE


def test_candidate_that_stops_firing_resolves_directly_never_active() -> None:
    """A CANDIDATE that stops firing before confirmation must resolve without ever having
    been ACTIVE — brief §7's "avoid alarm flapping" for a single-cycle blip."""
    decision = decide(
        row_exists=True,
        row_state=RuleFindingState.CANDIDATE,
        row_candidate_stable_cycles=1,
        fired=False,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.RESOLVE


def test_active_still_firing_refreshes() -> None:
    decision = decide(
        row_exists=True,
        row_state=RuleFindingState.ACTIVE,
        row_candidate_stable_cycles=0,
        fired=True,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.REFRESH_ACTIVE


def test_active_stops_firing_marks_recovering_not_resolved() -> None:
    """One clean cycle is not enough to resolve — avoids flapping on a single borderline
    cycle (brief §20, mirroring Phase 7's QualityIssue precedent)."""
    decision = decide(
        row_exists=True,
        row_state=RuleFindingState.ACTIVE,
        row_candidate_stable_cycles=0,
        fired=False,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.MARK_RECOVERING


def test_recovering_resolves_on_second_clean_cycle() -> None:
    decision = decide(
        row_exists=True,
        row_state=RuleFindingState.RECOVERING,
        row_candidate_stable_cycles=0,
        fired=False,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.RESOLVE


def test_recovering_that_fires_again_reactivates_never_actually_recovered() -> None:
    decision = decide(
        row_exists=True,
        row_state=RuleFindingState.RECOVERING,
        row_candidate_stable_cycles=0,
        fired=True,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.REACTIVATE_FROM_RECOVERING


def test_absent_row_not_firing_is_noop() -> None:
    decision = decide(
        row_exists=False,
        row_state=None,
        row_candidate_stable_cycles=0,
        fired=False,
        required_stable_cycles=3,
    )
    assert decision.action == LifecycleAction.NOOP


def test_required_stable_cycles_of_one_activates_immediately() -> None:
    """A rule configured with `required_stable_cycles=1` (e.g. RESERVOIR_LEVEL_LOW's faster
    confirmation) activates on its very first fire — no candidate phase needed."""
    decision = decide(
        row_exists=False,
        row_state=None,
        row_candidate_stable_cycles=0,
        fired=True,
        required_stable_cycles=1,
    )
    assert decision.action == LifecycleAction.CREATE_CANDIDATE
    # A second cycle with the counter already at 1 must activate, since 1 >= 1.
    decision2 = decide(
        row_exists=True,
        row_state=RuleFindingState.CANDIDATE,
        row_candidate_stable_cycles=1,
        fired=True,
        required_stable_cycles=1,
    )
    assert decision2.action == LifecycleAction.ACTIVATE
