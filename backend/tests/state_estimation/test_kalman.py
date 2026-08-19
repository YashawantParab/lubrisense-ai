"""Kalman predict/update mathematics (Phase 12 brief §35): determinism, partial
observation, variable dt, and state constraints, tested directly against the pure
`app.state_estimation.models.kalman` module — no config, no database, no feature vectors."""

from __future__ import annotations

import math

import pytest

from app.state_estimation.models import kalman


def _initial(p00: float = 0.1, p11: float = 0.001) -> kalman.State:
    return kalman.State(level=0.0, rate=0.0, p00=p00, p01=0.0, p11=p11)


def test_predict_is_deterministic() -> None:
    state = _initial()
    a = kalman.predict(state, 600.0, 1.0, 1e-7, 1e-11)
    b = kalman.predict(state, 600.0, 1.0, 1e-7, 1e-11)
    assert a == b


def test_predict_advances_level_by_rate_times_dt() -> None:
    state = kalman.State(level=0.2, rate=0.0001, p00=0.01, p01=0.0, p11=0.0001)
    result = kalman.predict(state, 100.0, 1.0, 0.0, 0.0)
    assert result.level == pytest.approx(0.2 + 0.0001 * 100.0)


def test_predict_grows_covariance_with_zero_process_noise_via_cross_terms() -> None:
    """Even with q_level=q_rate=0, P00 grows via the p01/p11 cross terms once they are
    nonzero (uncertainty propagates from rate into level over time) — process noise is not
    the only source of growth."""
    state = kalman.State(level=0.0, rate=0.0, p00=0.01, p01=0.001, p11=0.0001)
    result = kalman.predict(state, 100.0, 1.0, 0.0, 0.0)
    assert result.p00 > state.p00


def test_predict_zero_dt_leaves_level_and_rate_unchanged() -> None:
    state = kalman.State(level=0.3, rate=0.001, p00=0.05, p01=0.001, p11=0.0002)
    result = kalman.predict(state, 0.0, 1.0, 1e-7, 1e-11)
    assert result.level == pytest.approx(state.level)
    assert result.rate == pytest.approx(state.rate)
    # dt=0 process noise contribution is zero too.
    assert result.p00 == pytest.approx(state.p00)


def test_rate_retention_below_one_decays_rate_but_not_the_current_level_step() -> None:
    """A long gap (small `rate_retention`) still moves `level` by the full `rate*dt` for
    *this* step (using the rate as last known) but decays `rate` itself for the *next*
    step — the mean-reverting-velocity fix for outage extrapolation (see kalman.py's own
    module docstring)."""
    state = kalman.State(level=0.5, rate=0.0001, p00=0.01, p01=0.0, p11=0.0001)
    full_retention = kalman.predict(state, 1000.0, 1.0, 0.0, 0.0)
    decayed_retention = kalman.predict(state, 1000.0, 0.1, 0.0, 0.0)
    # Same level movement this step regardless of retention...
    assert full_retention.level == pytest.approx(decayed_retention.level)
    # ...but the decayed-retention rate carried forward is much smaller.
    assert decayed_retention.rate == pytest.approx(state.rate * 0.1)
    assert full_retention.rate == pytest.approx(state.rate)


def test_update_moves_level_toward_observation() -> None:
    state = _initial(p00=0.1)
    result = kalman.update(state, 0.8, 0.02)
    assert 0.0 < result.state.level < 0.8
    assert result.innovation == pytest.approx(0.8)


def test_update_reduces_level_variance() -> None:
    state = _initial(p00=0.1)
    result = kalman.update(state, 0.5, 0.02)
    assert result.state.p00 < state.p00


def test_update_is_deterministic() -> None:
    state = _initial(p00=0.1)
    a = kalman.update(state, 0.4, 0.03)
    b = kalman.update(state, 0.4, 0.03)
    assert a.state == b.state


def test_update_with_zero_or_negative_variance_rejected() -> None:
    state = _initial()
    with pytest.raises(ValueError, match="variance"):
        kalman.update(state, 0.5, 0.0)
    with pytest.raises(ValueError, match="variance"):
        kalman.update(state, 0.5, -1.0)


def test_first_update_does_not_move_rate_with_zero_initial_cross_covariance() -> None:
    """With p01=0 (no history connecting level and rate yet), a single update can only
    inform `level`, never `rate` — the Kalman gain for `rate` is `p01/S`, which is zero
    here. Rate only becomes observable once cross-covariance builds up via `predict`."""
    state = _initial(p00=0.1, p11=0.001)
    result = kalman.update(state, 0.9, 0.02)
    assert result.state.rate == pytest.approx(0.0)
    assert result.kalman_gain[1] == pytest.approx(0.0)


def test_sequential_updates_apply_multiple_channels_in_one_tick() -> None:
    """Two channels applied in sequence should pull the level further than either alone —
    the mechanism used for a tick with several available observation channels."""
    state = _initial(p00=0.1)
    one_channel = kalman.update(state, 0.8, 0.02).state
    r1 = kalman.update(state, 0.8, 0.02)
    two_channels = kalman.update(r1.state, 0.8, 0.02).state
    assert two_channels.level > one_channel.level
    assert two_channels.p00 < one_channel.p00


def test_clip_state_enforces_level_bounds() -> None:
    state = kalman.State(level=1.5, rate=0.0, p00=0.01, p01=0.0, p11=0.0001)
    clipped = kalman.clip_state(state, (0.0, 1.0), 0.01)
    assert clipped.level == 1.0

    state_low = kalman.State(level=-0.3, rate=0.0, p00=0.01, p01=0.0, p11=0.0001)
    clipped_low = kalman.clip_state(state_low, (0.0, 1.0), 0.01)
    assert clipped_low.level == 0.0


def test_clip_state_enforces_rate_bound() -> None:
    state = kalman.State(level=0.5, rate=5.0, p00=0.01, p01=0.0, p11=0.0001)
    clipped = kalman.clip_state(state, (0.0, 1.0), 0.02)
    assert clipped.rate == 0.02

    state_neg = kalman.State(level=0.5, rate=-5.0, p00=0.01, p01=0.0, p11=0.0001)
    clipped_neg = kalman.clip_state(state_neg, (0.0, 1.0), 0.02)
    assert clipped_neg.rate == -0.02


def test_clip_state_caps_runaway_covariance() -> None:
    huge = kalman.State(level=0.5, rate=0.0, p00=1e12, p01=0.0, p11=1e12)
    clipped = kalman.clip_state(huge, (0.0, 1.0), 0.01)
    assert math.isfinite(clipped.p00)
    assert clipped.p00 <= 1.0e6
    assert clipped.p11 <= 1.0e6


def test_predict_then_update_stays_finite_over_many_iterations() -> None:
    """No NaN/inf over a long chain of predict/update calls with reasonable inputs (Phase
    12 brief §13)."""
    state = _initial()
    for i in range(500):
        state = kalman.predict(state, 300.0, 0.99, 2e-7, 1e-11)
        result = kalman.update(state, 0.3 + 0.001 * i, 0.02)
        state = result.state
        assert math.isfinite(state.level)
        assert math.isfinite(state.rate)
        assert math.isfinite(state.p00)
        assert math.isfinite(state.p11)
