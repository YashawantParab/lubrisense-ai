from __future__ import annotations

import pytest

from simulator.domain.state import ReservoirState
from simulator.physics import reservoir


def test_consume_reduces_quantity_monotonically() -> None:
    state = ReservoirState(capacity_l=10.0, quantity_l=10.0)
    for _ in range(20):
        reservoir.consume(state, delivered_volume_cm3=50.0)
    assert state.quantity_l < 10.0
    assert state.quantity_l == pytest.approx(9.0)  # 20 * 50cm3 = 1000cm3 = 1L


def test_consume_never_goes_negative() -> None:
    state = ReservoirState(capacity_l=1.0, quantity_l=0.1)
    reservoir.consume(state, delivered_volume_cm3=10_000.0)
    assert state.quantity_l == 0.0


def test_consume_ignores_negative_delivery() -> None:
    state = ReservoirState(capacity_l=10.0, quantity_l=5.0)
    reservoir.consume(state, delivered_volume_cm3=-50.0)
    assert state.quantity_l == 5.0


def test_refill_sets_quantity_from_percent() -> None:
    state = ReservoirState(capacity_l=10.0, quantity_l=1.0)
    reservoir.refill(state, to_percent=100.0)
    assert state.quantity_l == 10.0
    reservoir.refill(state, to_percent=50.0)
    assert state.quantity_l == 5.0


def test_level_percent() -> None:
    state = ReservoirState(capacity_l=10.0, quantity_l=2.5)
    assert reservoir.level_percent(state) == 25.0


def test_level_percent_zero_capacity_is_zero_not_error() -> None:
    state = ReservoirState(capacity_l=0.0, quantity_l=0.0)
    assert reservoir.level_percent(state) == 0.0


def test_lubricant_temperature_relaxes_toward_ambient() -> None:
    state = ReservoirState(capacity_l=10.0, quantity_l=10.0, lubricant_temperature_c=22.0)
    reservoir.step_lubricant_temperature(
        state, ambient_temperature_c=30.0, pump_is_on=False, dt_s=300.0
    )
    assert 22.0 < state.lubricant_temperature_c < 30.0


def test_lubricant_temperature_slightly_higher_while_pump_running() -> None:
    off = ReservoirState(capacity_l=10.0, quantity_l=10.0, lubricant_temperature_c=22.0)
    on = ReservoirState(capacity_l=10.0, quantity_l=10.0, lubricant_temperature_c=22.0)
    for _ in range(50):
        reservoir.step_lubricant_temperature(
            off, ambient_temperature_c=22.0, pump_is_on=False, dt_s=10.0
        )
        reservoir.step_lubricant_temperature(
            on, ambient_temperature_c=22.0, pump_is_on=True, dt_s=10.0
        )
    assert on.lubricant_temperature_c > off.lubricant_temperature_c
