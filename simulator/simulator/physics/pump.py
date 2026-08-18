"""Pump model — pressure generation, motor current, and runtime (Phase 3 brief §8).

The pump does not jump to its target pressure; it approaches it with a first-order lag
whose time constant is inversely related to `efficiency` (a degraded pump builds pressure
more slowly and decays it more slowly too — both observable symptoms of Pump Degradation,
docs/FAILURE_MODE_CATALOG.md §8, even though Phase 3 itself only simulates the healthy
case). Motor current tracks pressure plus a fixed running baseline; it is near-idle whenever
the pump is off.
"""

from __future__ import annotations

import random

from simulator.config.loader import PumpConfig
from simulator.domain.state import PumpState
from simulator.physics.util import clip, exp_relax


def step_efficiency(
    pump: PumpState,
    config: PumpConfig,
    dt_s: float,
    rng: random.Random,
    *,
    efficiency_offset: float = 0.0,
) -> None:
    """Healthy pumps have efficiency that wanders very slightly around the configured
    default — not a fixed constant, but not a degradation trend either.

    `efficiency_offset` (Phase 4, docs/SCENARIO_ENGINE.md §5) is the Pump Degradation
    scenario's integration point: it shifts the relaxation *target* downward by a
    severity-scaled amount, so degradation appears as a real, lagged drift in the same
    efficiency value everything else already reads — not a second parallel state."""
    noise = rng.gauss(0.0, config.efficiency_noise_std)
    target = clip(config.efficiency_default - efficiency_offset + noise, 0.05, 1.0)
    pump.efficiency = exp_relax(pump.efficiency, target, dt_s, tau_s=120.0)


def step_pressure(
    pump: PumpState, target_pressure_bar: float, config: PumpConfig, dt_s: float
) -> None:
    """Pressure rises toward `target_pressure_bar` while the pump is on, and decays toward
    zero once it is off — both first-order lags, with degraded efficiency slowing the rise
    (never the decay, which is governed by line/circuit relief, not pump condition)."""
    if pump.is_on:
        tau = config.pressure_rise_time_constant_s / max(pump.efficiency, 0.05)
        pump.pressure_bar = exp_relax(pump.pressure_bar, target_pressure_bar, dt_s, tau)
    else:
        pump.pressure_bar = exp_relax(
            pump.pressure_bar, 0.0, dt_s, config.pressure_decay_time_constant_s
        )
    pump.pressure_bar = clip(pump.pressure_bar, 0.0, config.max_pressure_bar)


def step_current(pump: PumpState, config: PumpConfig) -> None:
    if pump.is_on:
        pump.motor_current_a = (
            config.current_running_base_a
            + config.current_pressure_gain_a_per_bar * pump.pressure_bar
        )
    else:
        pump.motor_current_a = config.current_idle_a


def step_runtime(pump: PumpState, dt_s: float) -> None:
    if pump.is_on:
        pump.runtime_s += dt_s
