"""Bearing condition model (Phase 3 brief §10).

Two deliberate design choices enforce the brief's "do NOT make vibration instantly rise
whenever pressure rises" requirement:

1. `lubrication_effectiveness` is only nudged at discrete lubrication-cycle-completion
   events (`on_cycle_result`), not from raw pressure/flow each tick — a bearing's actual
   lubrication state changes when lubricant is (or isn't) delivered, not when line pressure
   happens to be instantaneously higher or lower.
2. `temperature_c` and `vibration_rms_mm_s` both relax toward their targets through a
   first-order lag with a multi-minute time constant (`temperature_lag_time_constant_s`,
   `vibration_lag_time_constant_s`), so even a real change in `lubrication_effectiveness`
   takes real simulated time to show up in either signal — vibration lags further behind
   than temperature, matching typical bearing thermal vs. mechanical response time.
"""

from __future__ import annotations

from simulator.config.loader import BearingConfig
from simulator.domain.state import BearingState
from simulator.physics.util import clip, exp_relax


def on_cycle_result(bearing: BearingState, config: BearingConfig, delivered: bool) -> None:
    step = config.lubrication_recovery_step if delivered else -config.lubrication_decay_step
    bearing.lubrication_effectiveness = clip(bearing.lubrication_effectiveness + step, 0.0, 1.0)


def step_health(bearing: BearingState, config: BearingConfig, dt_s: float) -> None:
    dt_hours = dt_s / 3600.0
    starvation = clip(1.0 - bearing.lubrication_effectiveness, 0.0, 1.0)
    if starvation > 0.3:
        bearing.health -= config.health_degradation_per_hour_starved * dt_hours * starvation
    else:
        bearing.health += config.health_recovery_per_hour_lubricated * dt_hours
    bearing.health = clip(bearing.health, 0.0, 1.0)


def step_temperature(
    bearing: BearingState,
    config: BearingConfig,
    load_percent: float,
    ambient_temperature_c: float,
    dt_s: float,
    *,
    over_lubrication_severity: float = 0.0,
) -> None:
    target = (
        config.temperature_baseline_c
        + config.temperature_load_gain_c * (load_percent / 100.0)
        + config.temperature_lubrication_gain_c * (1.0 - bearing.lubrication_effectiveness)
        + config.temperature_ambient_gain * (ambient_temperature_c - 22.0)
        + config.temperature_degradation_gain_c * (1.0 - bearing.health)
        + config.temperature_over_lubrication_gain_c * over_lubrication_severity
    )
    bearing.temperature_c = exp_relax(
        bearing.temperature_c, target, dt_s, config.temperature_lag_time_constant_s
    )


def step_vibration(
    bearing: BearingState, config: BearingConfig, load_percent: float, dt_s: float
) -> None:
    degradation_term = (1.0 - bearing.health) * config.vibration_degradation_gain_mm_s
    target = (
        config.vibration_baseline_mm_s
        + config.vibration_load_gain_mm_s * (load_percent / 100.0)
        + config.vibration_lubrication_gain_mm_s * (1.0 - bearing.lubrication_effectiveness)
        + degradation_term
    )
    bearing.vibration_rms_mm_s = exp_relax(
        bearing.vibration_rms_mm_s, target, dt_s, config.vibration_lag_time_constant_s
    )
    bearing.vibration_peak_mm_s = bearing.vibration_rms_mm_s * config.vibration_peak_to_rms_ratio


def apply_independent_wear(
    bearing: BearingState, config: BearingConfig, target_health: float, dt_s: float
) -> None:
    """Independent Bearing Fault integration point (Phase 4,
    docs/FAILURE_MODE_CATALOG.md §12, docs/SCENARIO_ENGINE.md §5): relaxes `health` toward
    `target_health` (1.0 - fault severity) via a dedicated time constant, completely
    decoupled from `step_health`'s starvation-driven degradation/recovery — so an
    independent mechanical fault degrades `health` (and, through the existing
    `degradation_term` above, vibration/temperature) while `lubrication_effectiveness` and
    every lubrication-path signal remain entirely untouched. Only call this when a fault
    targeting this bearing is actually active; `target_health=1.0` would otherwise fight
    `step_health`'s own (much slower) healthy-recovery behavior for no reason."""
    bearing.health = exp_relax(bearing.health, target_health, dt_s, config.independent_wear_tau_s)
