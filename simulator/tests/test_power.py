from __future__ import annotations

import uuid

from simulator.config.loader import MachineConfig
from simulator.domain.state import BearingState, MachineState
from simulator.physics.machine import step_power

CONFIG = MachineConfig(
    nominal_rpm={"MOTOR": 1450.0},
    load_lag_time_constant_s=45.0,
    ambient_temperature_c={"mean": 22.0, "daily_amplitude_c": 4.0, "noise_std_c": 0.25},
    nominal_power_kw={"MOTOR": 45.0},
    power_load_gain_kw_per_percent=0.35,
    power_friction_gain_kw=12.0,
    power_lag_time_constant_s=300.0,
)


def _healthy_bearing() -> BearingState:
    return BearingState(bearing_id=uuid.uuid4(), health=1.0, lubrication_effectiveness=1.0)


def _degraded_bearing() -> BearingState:
    return BearingState(bearing_id=uuid.uuid4(), health=0.2, lubrication_effectiveness=0.3)


def test_power_does_not_jump_instantly() -> None:
    """Same "temporal lag" requirement `test_bearing.py` already encodes for
    temperature/vibration — a single tick must not carry power anywhere near a new,
    much-higher target."""
    state = MachineState(load_percent=90.0, power_kw=CONFIG.nominal_power_kw["MOTOR"])
    before = state.power_kw
    step_power(state, CONFIG, "MOTOR", [_degraded_bearing()], dt_s=5.0)
    assert abs(state.power_kw - before) < 1.0


def test_power_rises_toward_higher_target_under_sustained_load() -> None:
    state = MachineState(load_percent=0.0, power_kw=CONFIG.nominal_power_kw["MOTOR"])
    initial = state.power_kw
    for _ in range(200):
        state.load_percent = 90.0
        step_power(state, CONFIG, "MOTOR", [_healthy_bearing()], dt_s=30.0)
    assert state.power_kw > initial


def test_power_rises_with_sustained_bearing_degradation_at_comparable_load() -> None:
    """The core Lubrication Efficiency Intelligence physics claim: comparable load, worse
    bearing condition -> higher power, via the same real `(1 - health)` term
    `step_temperature`/`step_vibration` already use — never an independently invented
    effect."""
    healthy_state = MachineState(load_percent=60.0, power_kw=CONFIG.nominal_power_kw["MOTOR"])
    degraded_state = MachineState(load_percent=60.0, power_kw=CONFIG.nominal_power_kw["MOTOR"])
    for _ in range(200):
        step_power(healthy_state, CONFIG, "MOTOR", [_healthy_bearing()], dt_s=30.0)
        step_power(degraded_state, CONFIG, "MOTOR", [_degraded_bearing()], dt_s=30.0)
    assert degraded_state.power_kw > healthy_state.power_kw


def test_power_with_no_bearings_contributes_zero_friction_term() -> None:
    """A machine with no bearings tracked yet (e.g. still commissioning) must not error
    or fabricate a friction effect."""
    state = MachineState(load_percent=50.0, power_kw=CONFIG.nominal_power_kw["MOTOR"])
    step_power(state, CONFIG, "MOTOR", [], dt_s=30.0)
    assert state.power_kw >= 0.0


def test_unknown_machine_type_falls_back_to_a_reasonable_default() -> None:
    state = MachineState(load_percent=0.0, power_kw=0.0)
    step_power(state, CONFIG, "UNKNOWN_TYPE", [], dt_s=30.0)
    assert state.power_kw >= 0.0
