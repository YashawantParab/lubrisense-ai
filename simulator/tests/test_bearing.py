from __future__ import annotations

import uuid

from simulator.config.loader import BearingConfig
from simulator.domain.state import BearingState
from simulator.physics import bearing

CONFIG = BearingConfig(
    temperature_baseline_c=38.0,
    temperature_load_gain_c=16.0,
    temperature_ambient_gain=0.3,
    temperature_lubrication_gain_c=14.0,
    temperature_lag_time_constant_s=600.0,
    temperature_degradation_gain_c=6.0,
    temperature_over_lubrication_gain_c=3.0,
    vibration_baseline_mm_s=1.1,
    vibration_load_gain_mm_s=0.8,
    vibration_lubrication_gain_mm_s=1.8,
    vibration_lag_time_constant_s=900.0,
    vibration_peak_to_rms_ratio=1.6,
    vibration_degradation_gain_mm_s=3.0,
    lubrication_recovery_step=0.06,
    lubrication_decay_step=0.10,
    health_degradation_per_hour_starved=0.0006,
    health_recovery_per_hour_lubricated=0.00003,
    independent_wear_tau_s=1800.0,
)


def _bearing() -> BearingState:
    return BearingState(
        bearing_id=uuid.uuid4(),
        temperature_c=CONFIG.temperature_baseline_c,
        vibration_rms_mm_s=CONFIG.vibration_baseline_mm_s,
    )


def test_temperature_rises_toward_higher_target_under_load() -> None:
    b = _bearing()
    initial = b.temperature_c
    for _ in range(120):
        bearing.step_temperature(
            b, CONFIG, load_percent=90.0, ambient_temperature_c=22.0, dt_s=30.0
        )
    assert b.temperature_c > initial


def test_temperature_does_not_jump_instantly() -> None:
    """A single tick must not carry the bearing anywhere near its new steady-state target —
    this is the "temporal lag" requirement (Phase 3 brief §10)."""
    b = _bearing()
    before = b.temperature_c
    bearing.step_temperature(b, CONFIG, load_percent=100.0, ambient_temperature_c=22.0, dt_s=5.0)
    assert abs(b.temperature_c - before) < 1.0


def test_vibration_does_not_instantly_react_to_lubrication_change() -> None:
    """Directly encodes the brief's "do NOT make vibration instantly rise whenever pressure
    rises" requirement: even a full swing in lubrication_effectiveness must not produce a
    large vibration jump in a single tick."""
    b = _bearing()
    before = b.vibration_rms_mm_s
    b.lubrication_effectiveness = 0.0  # worst case, instantaneous
    bearing.step_vibration(b, CONFIG, load_percent=50.0, dt_s=5.0)
    assert abs(b.vibration_rms_mm_s - before) < 0.05


def test_vibration_eventually_rises_with_sustained_starvation() -> None:
    b = _bearing()
    healthy_vibration = b.vibration_rms_mm_s
    b.lubrication_effectiveness = 0.0
    for _ in range(400):
        bearing.step_vibration(b, CONFIG, load_percent=50.0, dt_s=30.0)
    assert b.vibration_rms_mm_s > healthy_vibration


def test_vibration_peak_derived_from_rms() -> None:
    b = _bearing()
    bearing.step_vibration(b, CONFIG, load_percent=50.0, dt_s=5.0)
    assert b.vibration_peak_mm_s == b.vibration_rms_mm_s * CONFIG.vibration_peak_to_rms_ratio


def test_lubrication_effectiveness_nudged_by_cycle_result_not_by_pressure() -> None:
    b = _bearing()
    assert b.lubrication_effectiveness == 1.0
    bearing.on_cycle_result(b, CONFIG, delivered=False)
    assert b.lubrication_effectiveness == 1.0 - CONFIG.lubrication_decay_step
    bearing.on_cycle_result(b, CONFIG, delivered=True)
    assert b.lubrication_effectiveness > 1.0 - CONFIG.lubrication_decay_step


def test_lubrication_effectiveness_bounded_0_1() -> None:
    b = _bearing()
    for _ in range(50):
        bearing.on_cycle_result(b, CONFIG, delivered=True)
    assert b.lubrication_effectiveness <= 1.0
    for _ in range(50):
        bearing.on_cycle_result(b, CONFIG, delivered=False)
    assert b.lubrication_effectiveness >= 0.0


def test_health_degrades_under_sustained_starvation() -> None:
    b = _bearing()
    b.lubrication_effectiveness = 0.0
    for _ in range(2000):
        bearing.step_health(b, CONFIG, dt_s=60.0)
    assert b.health < 1.0
    assert b.health >= 0.0


def test_health_stable_when_well_lubricated() -> None:
    b = _bearing()
    for _ in range(1000):
        bearing.step_health(b, CONFIG, dt_s=60.0)
    assert b.health >= 1.0 - 1e-6
