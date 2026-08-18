from __future__ import annotations

import random

from simulator.config.loader import CircuitConfig
from simulator.domain.state import CircuitState
from simulator.physics import circuit

CONFIG = CircuitConfig(
    base_resistance=1.0,
    resistance_gain_restriction=6.0,
    leakage_pressure_loss_gain=0.3,
    default_restriction_factor=0.02,
    default_leakage_factor=0.01,
    restriction_noise_std=0.01,
)


def test_resistance_ratio_is_one_at_zero_restriction() -> None:
    state = CircuitState(restriction_factor=0.0, leakage_factor=0.0)
    assert circuit.resistance_ratio(state, CONFIG) == 1.0


def test_higher_restriction_increases_resistance_ratio() -> None:
    low = CircuitState(restriction_factor=0.05, leakage_factor=0.0)
    high = CircuitState(restriction_factor=0.5, leakage_factor=0.0)
    assert circuit.resistance_ratio(high, CONFIG) > circuit.resistance_ratio(low, CONFIG)


def test_higher_restriction_reduces_delivered_flow() -> None:
    low = CircuitState(restriction_factor=0.02, leakage_factor=0.0)
    high = CircuitState(restriction_factor=0.6, leakage_factor=0.0)
    op_low = circuit.solve_operating_point(low, CONFIG, 9.0, 90.0, pump_efficiency=1.0)
    op_high = circuit.solve_operating_point(high, CONFIG, 9.0, 90.0, pump_efficiency=1.0)
    assert op_high.delivered_flow_cm3_min < op_low.delivered_flow_cm3_min


def test_higher_restriction_increases_required_pressure() -> None:
    low = CircuitState(restriction_factor=0.02, leakage_factor=0.0)
    high = CircuitState(restriction_factor=0.6, leakage_factor=0.0)
    op_low = circuit.solve_operating_point(low, CONFIG, 9.0, 90.0, pump_efficiency=1.0)
    op_high = circuit.solve_operating_point(high, CONFIG, 9.0, 90.0, pump_efficiency=1.0)
    assert op_high.required_pressure_bar > op_low.required_pressure_bar


def test_leakage_reduces_delivered_flow() -> None:
    no_leak = CircuitState(restriction_factor=0.02, leakage_factor=0.0)
    leaking = CircuitState(restriction_factor=0.02, leakage_factor=0.3)
    op_no_leak = circuit.solve_operating_point(no_leak, CONFIG, 9.0, 90.0, pump_efficiency=1.0)
    op_leaking = circuit.solve_operating_point(leaking, CONFIG, 9.0, 90.0, pump_efficiency=1.0)
    assert op_leaking.delivered_flow_cm3_min < op_no_leak.delivered_flow_cm3_min


def test_lower_pump_efficiency_reduces_delivered_flow() -> None:
    state = CircuitState(restriction_factor=0.02, leakage_factor=0.0)
    op_full = circuit.solve_operating_point(state, CONFIG, 9.0, 90.0, pump_efficiency=1.0)
    op_degraded = circuit.solve_operating_point(state, CONFIG, 9.0, 90.0, pump_efficiency=0.5)
    assert op_degraded.delivered_flow_cm3_min < op_full.delivered_flow_cm3_min


def test_backpressure_reduced_by_leakage() -> None:
    no_leak = CircuitState(restriction_factor=0.0, leakage_factor=0.0)
    leaking = CircuitState(restriction_factor=0.0, leakage_factor=0.5)
    assert circuit.circuit_backpressure_bar(
        10.0, leaking, CONFIG
    ) < circuit.circuit_backpressure_bar(10.0, no_leak, CONFIG)


def test_flow_never_negative() -> None:
    state = CircuitState(restriction_factor=1.0, leakage_factor=1.0)
    op = circuit.solve_operating_point(state, CONFIG, 9.0, 90.0, pump_efficiency=0.01)
    assert op.delivered_flow_cm3_min >= 0.0


def test_natural_variation_stays_bounded_and_deterministic_for_seed() -> None:
    rng_a = random.Random(7)
    rng_b = random.Random(7)
    state_a = CircuitState(restriction_factor=CONFIG.default_restriction_factor, leakage_factor=0.0)
    state_b = CircuitState(restriction_factor=CONFIG.default_restriction_factor, leakage_factor=0.0)
    for _ in range(200):
        circuit.step_natural_variation(state_a, CONFIG, dt_s=5.0, rng=rng_a)
        circuit.step_natural_variation(state_b, CONFIG, dt_s=5.0, rng=rng_b)
        assert 0.0 <= state_a.restriction_factor <= CONFIG.default_restriction_factor + 0.05
    assert state_a.restriction_factor == state_b.restriction_factor
