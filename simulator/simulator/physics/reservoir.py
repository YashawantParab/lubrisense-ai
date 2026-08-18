"""Reservoir model — stateful lubricant quantity tracking (Phase 3 brief §7).

The reservoir only loses quantity through delivered lubrication (`consume`) and only gains
quantity through an explicit `refill` (Phase 4 brief §24 — a synthetic operational event,
never a failure mode). Sensor noise is applied later, only at the sensor-model layer
(`simulator.sensors`) — the true physical `quantity_l` here is always monotonically
non-increasing between refills.

`availability_factor` is the Phase 4 Low Reservoir integration point (docs/SCENARIO_ENGINE.md
§6): as the reservoir approaches empty, the pump can no longer draw its full nominal flow —
`simulator.physics.cycle` multiplies delivered flow by this factor, so a starved reservoir
degrades cycle delivery *physically* (through the existing flow pathway) rather than the
Low Reservoir scenario directly touching any sensor value.
"""

from __future__ import annotations

from simulator.config.loader import ReservoirConfig
from simulator.domain.enums import ReservoirLevelState
from simulator.domain.state import ReservoirState
from simulator.physics.util import clip, exp_relax


def consume(reservoir: ReservoirState, delivered_volume_cm3: float) -> None:
    delivered_l = max(0.0, delivered_volume_cm3) / 1000.0
    reservoir.quantity_l = max(0.0, reservoir.quantity_l - delivered_l)


def refill(reservoir: ReservoirState, to_percent: float = 100.0) -> None:
    reservoir.quantity_l = reservoir.capacity_l * clip(to_percent, 0.0, 100.0) / 100.0


def level_percent(reservoir: ReservoirState) -> float:
    if reservoir.capacity_l <= 0:
        return 0.0
    return clip(100.0 * reservoir.quantity_l / reservoir.capacity_l, 0.0, 100.0)


def level_state(reservoir: ReservoirState, config: ReservoirConfig) -> ReservoirLevelState:
    """Ground-truth-only qualitative band — never itself a sensor reading."""
    pct = level_percent(reservoir)
    if pct <= config.empty_level_percent:
        return ReservoirLevelState.EMPTY
    if pct <= config.critical_level_percent:
        return ReservoirLevelState.CRITICAL
    if pct <= config.low_level_warning_percent:
        return ReservoirLevelState.LOW
    return ReservoirLevelState.NORMAL


def availability_factor(reservoir: ReservoirState, config: ReservoirConfig) -> float:
    """1.0 while the reservoir has ample lubricant; ramps linearly to 0.0 between
    `critical_level_percent` and `empty_level_percent` — the pump physically cannot draw
    flow it does not have. See module docstring."""
    pct = level_percent(reservoir)
    if pct >= config.critical_level_percent:
        return 1.0
    if pct <= config.empty_level_percent:
        return 0.0
    span = config.critical_level_percent - config.empty_level_percent
    if span <= 0:
        return 0.0
    return clip((pct - config.empty_level_percent) / span, 0.0, 1.0)


def step_lubricant_temperature(
    reservoir: ReservoirState, ambient_temperature_c: float, pump_is_on: bool, dt_s: float
) -> None:
    """Lubricant temperature slowly tracks ambient, with a small additional rise while the
    pump is actively running (mechanical/friction heat) — a lagged, explainable
    simplification, not a thermal simulation."""
    target = ambient_temperature_c + (2.0 if pump_is_on else 0.0)
    reservoir.lubricant_temperature_c = exp_relax(
        reservoir.lubricant_temperature_c, target, dt_s, tau_s=300.0
    )
