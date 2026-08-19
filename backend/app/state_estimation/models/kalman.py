"""A standard 2-state linear Kalman filter (Phase 12 brief §6), implemented with plain
Python floats/tuples — no numpy dependency, since the state is fixed at 2x1 and every
matrix below is written out explicitly precisely so nothing is a hidden/opaque operation.

State-space elements, in this system's terms (docs/STATE_ESTIMATION.md "Kalman model" has
the full write-up):

    x_k  -- 2x1 state vector [level, rate]. `level` is the normalized condition state in
             [0, 1] (0 = nominal, 1 = severely degraded, Phase 12 brief §3); `rate` is its
             instantaneous rate of change, in level-units per second.
    F    -- 2x2 state-transition matrix for a mean-reverting-velocity model over `dt`
             seconds: level_next = level + rate*dt ; rate_next = rate * g, where
             g = exp(-dt / rate_decay_tau_seconds) is the "rate retention" for this step
             (`ObservationChannelConfig`'s sibling `rate_decay_tau_seconds` in
             `StateTypeConfig`). A pure constant-velocity model (g == 1 always) was tried
             first and rejected: over a short dt (a materialized tick, ~minutes) g ~= 1 so
             short-horizon behavior is unchanged, but over a long real gap (a multi-hour
             outage) a pure constant-velocity model extrapolates whatever rate was last
             estimated indefinitely into the future — verified live to swing the level
             estimate all the way toward 0 during a simulated multi-hour outage that
             started from a settling-but-still-slightly-negative rate, i.e. communication
             failure was turning into a fabricated *recovery*, the false-confidence problem
             from the opposite direction (Phase 12 brief §27, §11). Decaying `rate` toward
             zero as `g -> 0` for long gaps (while covariance growth via `Q` still and
             separately drives `uncertainty` to `HIGH`) fixes this without touching the
             short-horizon dynamics validated against the fault scenarios — see
             docs/STATE_ESTIMATION.md "Kalman model" and the corresponding ADR.
    H    -- 1x2 observation matrix for one scalar evidence channel: z = H @ x + noise,
             with H = [1, 0] (every channel observes `level` directly; none observes
             `rate` directly — see `ObservationChannelConfig`/the calibration transform in
             `app.state_estimation.models.estimator` for how a raw Phase 10 feature becomes
             this scalar `z`).
    Q(dt)-- 2x2 process-noise covariance, `diag(q_level*dt, q_rate*dt)` — see
             `state_estimation_v1.yaml`'s own comment for why this simpler independent-
             diffusion form was chosen over the textbook coupled white-noise-acceleration
             form.
    R    -- scalar measurement-noise variance for one channel at one tick (already quality-
             inflated by the caller before this module ever sees it).
    P    -- 2x2 state-covariance matrix (uncertainty in `x`).

Every function here is a pure, deterministic transform over its inputs — no I/O, no
config-file reads, no hidden global state — precisely so the math itself is trivially
unit-testable in isolation from the rest of the estimator.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A pure numerical-overflow guard on the covariance terms, not a semantic/tunable
#: parameter — `StateTypeConfig.uncertainty` thresholds already saturate the *reported*
#: `LOW`/`MODERATE`/`HIGH` category well below this; this only stops covariance from
#: growing without bound across an arbitrarily long, sparsely-observed replay sequence
#: (Phase 12 brief §13).
_MAX_VARIANCE = 1.0e6


@dataclass(frozen=True, slots=True)
class State:
    """`x_k` plus `P` together — the complete recoverable state of one filter instance
    between calls. Immutable; every operation below returns a new `State`."""

    level: float
    rate: float
    p00: float  # Var(level)
    p01: float  # Cov(level, rate) == p10 (P is symmetric)
    p11: float  # Var(rate)


def predict(state: State, dt: float, rate_retention: float, q_level: float, q_rate: float) -> State:
    """x_k|k-1 = F @ x_k-1|k-1 ; P_k|k-1 = F @ P_k-1|k-1 @ F.T + Q(dt), for
    F = [[1, dt], [0, g]] with g = `rate_retention` (see the module docstring for why `g`
    is not always 1).

    `dt` and `rate_retention` must already be computed/clamped by the caller
    (`app.state_estimation.models.estimator` applies `GapPolicy.min_dt_seconds`/
    `max_dt_seconds` and derives `g = exp(-dt / tau)` — this function trusts its inputs and
    does not re-validate, so it stays a pure, allocation-free numeric transform).
    """
    level = state.level + state.rate * dt
    rate = state.rate * rate_retention

    # F @ P @ F.T for F = [[1, dt], [0, g]], written out termwise (F @ P first, then that
    # result @ F.T) so every term is inspectable:
    #   (F @ P)      = [[p00 + dt*p01, p01 + dt*p11],
    #                   [g*p01,        g*p11       ]]
    #   (F @ P)@F.T  = [[p00 + 2*dt*p01 + dt^2*p11, g*p01 + g*dt*p11],
    #                   [g*p01 + g*dt*p11,           g^2*p11        ]]
    p00 = state.p00 + 2.0 * dt * state.p01 + dt * dt * state.p11
    p01_sym = rate_retention * state.p01 + rate_retention * dt * state.p11
    p11 = rate_retention * rate_retention * state.p11

    return State(
        level=level,
        rate=rate,
        p00=p00 + q_level * dt,
        p01=p01_sym,
        p11=p11 + q_rate * dt,
    )


@dataclass(frozen=True, slots=True)
class UpdateResult:
    state: State
    innovation: float  # z - H @ x_predicted, kept for diagnostics/tests
    kalman_gain: tuple[float, float]  # (K for level, K for rate), kept for diagnostics


def update(state: State, z: float, r: float) -> UpdateResult:
    """Scalar measurement update for one observation channel with H = [1, 0] (`z` observes
    `level` directly): innovation y = z - H@x ; S = H@P@H.T + R ; K = P@H.T @ S^-1 ;
    x_k|k = x_k|k-1 + K*y ; P_k|k = (I - K@H) @ P_k|k-1.

    Multiple channels in one tick are applied by calling this function once per channel in
    sequence, each time feeding in the previous call's output `state` — mathematically
    equivalent to one batched vector update with a diagonal R (channels are modeled as
    conditionally independent given the state), and far simpler to reason about when the
    number of available channels varies tick to tick (Phase 12 brief §10: partial
    observations must not require resizing H/R).
    """
    if r <= 0:
        raise ValueError("measurement variance R must be > 0")

    innovation = z - state.level  # H @ x == level, since H = [1, 0]
    s = state.p00 + r  # H @ P @ H.T + R, H = [1, 0] -> just p00
    if s <= 0:
        raise ValueError("innovation covariance S must be > 0")

    k_level = state.p00 / s
    k_rate = state.p01 / s

    level = state.level + k_level * innovation
    rate = state.rate + k_rate * innovation

    # (I - K@H) @ P, H = [1, 0] so K@H = [[k_level, 0], [k_rate, 0]]:
    #   (I - K@H) = [[1-k_level, 0], [-k_rate, 1]]
    #   (I - K@H) @ P = [[(1-k_level)*p00,        (1-k_level)*p01       ],
    #                    [-k_rate*p00 + p01(old), -k_rate*p01(old)+p11 ]]
    p00 = (1.0 - k_level) * state.p00
    p01 = (1.0 - k_level) * state.p01
    p10 = -k_rate * state.p00 + state.p01
    p11 = -k_rate * state.p01 + state.p11
    p01_sym = (p01 + p10) / 2.0

    new_state = State(level=level, rate=rate, p00=p00, p01=p01_sym, p11=p11)
    return UpdateResult(state=new_state, innovation=innovation, kalman_gain=(k_level, k_rate))


def clip_state(state: State, level_bounds: tuple[float, float], rate_bound: float) -> State:
    """Enforce the configured state constraints (Phase 12 brief §13): `level` stays within
    `level_bounds`, `rate` stays within `[-rate_bound, rate_bound]`. Covariance terms are
    left untouched — clipping the mean does not imply the estimator is suddenly certain,
    and NaN/inf can only originate from `predict`/`update` themselves given finite, valid
    inputs (both are pure polynomial arithmetic with no division except by `S`/`p00+r`,
    which the `r <= 0`/`s <= 0` guards above already make unreachable-as-zero)."""
    low, high = level_bounds
    level = min(max(state.level, low), high)
    rate = min(max(state.rate, -rate_bound), rate_bound)
    p00 = min(state.p00, _MAX_VARIANCE)
    p11 = min(state.p11, _MAX_VARIANCE)
    return State(level=level, rate=rate, p00=p00, p01=state.p01, p11=p11)
