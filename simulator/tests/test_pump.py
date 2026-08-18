from __future__ import annotations

import random

from simulator.config.loader import PumpConfig
from simulator.domain.state import PumpState
from simulator.physics import pump

CONFIG = PumpConfig(
    base_operating_pressure_bar=9.0,
    max_pressure_bar=18.0,
    nominal_flow_capacity_cm3_min=90.0,
    pressure_rise_time_constant_s=6.0,
    pressure_decay_time_constant_s=10.0,
    current_idle_a=0.05,
    current_running_base_a=1.4,
    current_pressure_gain_a_per_bar=0.12,
    efficiency_default=0.97,
    efficiency_noise_std=0.004,
)


def test_pressure_rises_toward_target_when_on() -> None:
    state = PumpState(efficiency=0.97, is_on=True)
    for _ in range(30):
        pump.step_pressure(state, target_pressure_bar=9.0, config=CONFIG, dt_s=1.0)
    assert 8.5 < state.pressure_bar <= 9.0


def test_pressure_decays_when_off() -> None:
    state = PumpState(efficiency=0.97, is_on=False, pressure_bar=9.0)
    for _ in range(60):
        pump.step_pressure(state, target_pressure_bar=0.0, config=CONFIG, dt_s=1.0)
    assert state.pressure_bar < 0.5


def test_pressure_never_exceeds_max() -> None:
    state = PumpState(efficiency=1.0, is_on=True)
    for _ in range(200):
        pump.step_pressure(state, target_pressure_bar=100.0, config=CONFIG, dt_s=5.0)
    assert state.pressure_bar <= CONFIG.max_pressure_bar


def test_degraded_efficiency_slows_pressure_rise() -> None:
    healthy = PumpState(efficiency=1.0, is_on=True)
    degraded = PumpState(efficiency=0.5, is_on=True)
    for _ in range(5):
        pump.step_pressure(healthy, target_pressure_bar=9.0, config=CONFIG, dt_s=1.0)
        pump.step_pressure(degraded, target_pressure_bar=9.0, config=CONFIG, dt_s=1.0)
    assert degraded.pressure_bar < healthy.pressure_bar


def test_current_is_idle_when_off() -> None:
    state = PumpState(pressure_bar=5.0, is_on=False)
    pump.step_current(state, CONFIG)
    assert state.motor_current_a == CONFIG.current_idle_a


def test_current_scales_with_pressure_when_on() -> None:
    low = PumpState(pressure_bar=2.0, is_on=True)
    high = PumpState(pressure_bar=15.0, is_on=True)
    pump.step_current(low, CONFIG)
    pump.step_current(high, CONFIG)
    assert high.motor_current_a > low.motor_current_a > CONFIG.current_idle_a


def test_runtime_only_accumulates_while_on() -> None:
    state = PumpState(is_on=False)
    pump.step_runtime(state, dt_s=10.0)
    assert state.runtime_s == 0.0
    state.is_on = True
    pump.step_runtime(state, dt_s=10.0)
    assert state.runtime_s == 10.0


def test_efficiency_wanders_near_default_but_stays_bounded() -> None:
    rng = random.Random(1)
    state = PumpState(efficiency=CONFIG.efficiency_default)
    for _ in range(500):
        pump.step_efficiency(state, CONFIG, dt_s=5.0, rng=rng)
        assert 0.5 <= state.efficiency <= 1.0
    assert abs(state.efficiency - CONFIG.efficiency_default) < 0.05
