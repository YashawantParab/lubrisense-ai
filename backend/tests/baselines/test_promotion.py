"""Unit tests for the contamination-control state machine
(`app.baselines.services.promotion.decide`) — pure function, no database. This is the
safety-critical logic Phase 8 brief §39/§40/§41 requires: a developing fault must never
immediately redefine normal.
"""

from __future__ import annotations

from app.baselines.config.policy import StabilityGatePolicy
from app.baselines.services.promotion import UpdateAction, decide
from app.domain.enums import BaselineMetricKind, BaselineState

GATE = StabilityGatePolicy(required_stable_cycles=2, candidate_divergence_mad_multiplier=3.0)


def _stats(median: float, mad: float = 2.0) -> dict[str, float]:
    return {"median": median, "mad": mad}


def test_no_row_insufficient_samples_creates_insufficient() -> None:
    decision = decide(
        row_exists=False,
        row_state=None,
        row_statistics=None,
        row_candidate_statistics=None,
        row_candidate_stable_cycles=0,
        new_stats=_stats(50.0),
        new_sample_count=5,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert decision.action == UpdateAction.CREATE_INSUFFICIENT


def test_existing_row_insufficient_samples_freezes() -> None:
    decision = decide(
        row_exists=True,
        row_state=BaselineState.ACTIVE,
        row_statistics=_stats(50.0),
        row_candidate_statistics=None,
        row_candidate_stable_cycles=0,
        new_stats=None,
        new_sample_count=0,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert decision.action == UpdateAction.FREEZE


def test_no_row_enough_samples_starts_candidate() -> None:
    decision = decide(
        row_exists=False,
        row_state=None,
        row_statistics=None,
        row_candidate_statistics=None,
        row_candidate_stable_cycles=0,
        new_stats=_stats(50.0),
        new_sample_count=40,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert decision.action == UpdateAction.START_CANDIDATE
    assert decision.candidate_stable_cycles == 1


def test_first_activation_requires_two_stable_cycles() -> None:
    # Cycle 1: BUILDING row already has a candidate from a previous cycle; new stats match.
    decision = decide(
        row_exists=True,
        row_state=BaselineState.BUILDING,
        row_statistics=None,
        row_candidate_statistics=_stats(50.0),
        row_candidate_stable_cycles=1,
        new_stats=_stats(50.5),
        new_sample_count=40,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert decision.action == UpdateAction.ACTIVATE


def test_first_candidate_that_immediately_moves_restarts() -> None:
    decision = decide(
        row_exists=True,
        row_state=BaselineState.BUILDING,
        row_statistics=None,
        row_candidate_statistics=_stats(50.0, mad=1.0),
        row_candidate_stable_cycles=1,
        new_stats=_stats(80.0, mad=1.0),  # way outside 3x MAD of 50.0
        new_sample_count=40,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert decision.action == UpdateAction.START_CANDIDATE
    assert decision.candidate_stable_cycles == 1


def test_matching_active_anchor_refines_in_place() -> None:
    decision = decide(
        row_exists=True,
        row_state=BaselineState.ACTIVE,
        row_statistics=_stats(50.0, mad=2.0),
        row_candidate_statistics=None,
        row_candidate_stable_cycles=0,
        new_stats=_stats(50.8, mad=2.0),  # well within 3x MAD
        new_sample_count=40,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert decision.action == UpdateAction.REFINE_ACTIVE


def test_single_cycle_deviation_from_active_never_promotes_immediately() -> None:
    """A one-cycle blip that diverges from the anchor must start candidate tracking, not
    promote outright — brief §39's core requirement."""
    decision = decide(
        row_exists=True,
        row_state=BaselineState.ACTIVE,
        row_statistics=_stats(50.0, mad=1.0),
        row_candidate_statistics=None,
        row_candidate_stable_cycles=0,
        new_stats=_stats(80.0, mad=1.0),  # far outside anchor tolerance
        new_sample_count=40,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert decision.action == UpdateAction.START_CANDIDATE
    assert decision.candidate_stable_cycles == 1


def test_gradual_drift_never_promotes_while_still_moving() -> None:
    """Simulates a slow, continuous drift: each cycle's candidate is measurably further
    from the *previous* candidate than tolerance allows (still trending), so it must never
    reach PROMOTE — this is the "boiling frog" failure mode the anchor-based design exists
    to prevent (brief §39/§41)."""
    anchor = _stats(50.0, mad=1.0)
    candidate_history: dict[str, float] | None = None
    stable_cycles = 0
    state = BaselineState.ACTIVE
    drifting_values = [
        56.0,
        62.0,
        68.0,
        74.0,
        80.0,
    ]  # +6 each cycle, mad=1 -> always > 3x MAD apart
    promoted = False
    for value in drifting_values:
        decision = decide(
            row_exists=True,
            row_state=state,
            row_statistics=anchor,
            row_candidate_statistics=candidate_history,
            row_candidate_stable_cycles=stable_cycles,
            new_stats=_stats(value, mad=1.0),
            new_sample_count=40,
            min_sample_required=30,
            metric_kind=BaselineMetricKind.STANDARD,
            stability_gate=GATE,
        )
        assert decision.action in (UpdateAction.START_CANDIDATE, UpdateAction.ADVANCE_CANDIDATE)
        if decision.action == UpdateAction.PROMOTE:
            promoted = True
        candidate_history = _stats(value, mad=1.0)
        stable_cycles = decision.candidate_stable_cycles
    assert not promoted


def test_settled_drift_eventually_promotes_after_stabilizing() -> None:
    """Once the new level stops moving (two consecutive cycles agree with each other),
    promotion is allowed — the anchor stays fixed until then (brief §41's "activation
    requires stability window")."""
    anchor = _stats(50.0, mad=1.0)
    # Cycle 1: jumps to a new level, starts candidate tracking.
    d1 = decide(
        row_exists=True,
        row_state=BaselineState.ACTIVE,
        row_statistics=anchor,
        row_candidate_statistics=None,
        row_candidate_stable_cycles=0,
        new_stats=_stats(80.0, mad=1.0),
        new_sample_count=40,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert d1.action == UpdateAction.START_CANDIDATE

    # Cycle 2: settles at the same new level as cycle 1 -> confirmed stable -> PROMOTE.
    d2 = decide(
        row_exists=True,
        row_state=BaselineState.ACTIVE,
        row_statistics=anchor,  # anchor unchanged the whole time
        row_candidate_statistics=_stats(80.0, mad=1.0),
        row_candidate_stable_cycles=d1.candidate_stable_cycles,
        new_stats=_stats(80.2, mad=1.0),
        new_sample_count=40,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert d2.action == UpdateAction.PROMOTE


def test_stale_row_matching_anchor_recovers_to_active() -> None:
    decision = decide(
        row_exists=True,
        row_state=BaselineState.STALE,
        row_statistics=_stats(50.0, mad=2.0),
        row_candidate_statistics=None,
        row_candidate_stable_cycles=0,
        new_stats=_stats(50.5, mad=2.0),
        new_sample_count=40,
        min_sample_required=30,
        metric_kind=BaselineMetricKind.STANDARD,
        stability_gate=GATE,
    )
    assert decision.action == UpdateAction.REFINE_ACTIVE
