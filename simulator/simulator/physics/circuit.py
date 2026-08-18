"""Circuit / flow-resistance model — a deliberately simple, explainable reduced-order
model (Phase 3 brief §9), not a CFD simulation and not a proprietary hydraulic model.

Analogy: `resistance` behaves like an electrical resistance. A circuit's resistance rises
with `restriction_factor` (a developing blockage); for a given pump driving pressure, flow
falls as resistance rises (`flow = pump_flow_capacity / resistance_ratio`), and the pressure
required to push the pump's nominal flow through a more-restricted circuit rises
correspondingly (`required_pressure = base_pressure * resistance_ratio`). `leakage_factor`
represents lubricant lost before reaching the lubrication point.

Phase 4 (docs/SCENARIO_ENGINE.md §5) splits flow into two figures to make Gradual
Restriction/Sudden Blockage physically distinct from Leakage rather than reusing one signal
with a different label:

- `raw_flow_cm3_min`: what the pump actually draws from the reservoir — governed by
  `restriction_factor` (and pump efficiency) only. A leak downstream of the pump does not
  change how hard the pump has to work or how much it draws.
- `delivered_flow_cm3_min` = `raw_flow_cm3_min * (1 - leakage_factor)`: what actually
  reaches the lubrication point/bearing. Restriction reduces *both* figures together
  (nothing is lost, less is simply pushed through); leakage reduces only the delivered
  figure while raw (and therefore reservoir consumption) stays normal — "the numbers add up
  on the pump side, but the bearing isn't getting lubricated."
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulator.config.loader import CircuitConfig
from simulator.domain.state import CircuitState
from simulator.physics.util import clip, exp_relax


@dataclass(frozen=True, slots=True)
class CircuitOperatingPoint:
    resistance_ratio: float  # 1.0 = clean baseline circuit
    required_pressure_bar: float
    raw_flow_cm3_min: float  # what the pump draws — see module docstring
    delivered_flow_cm3_min: float  # what reaches the lubrication point (post-leak)


def resistance_ratio(circuit: CircuitState, config: CircuitConfig) -> float:
    """>= 1.0; grows with restriction_factor. 1.0 at restriction_factor == 0."""
    return 1.0 + circuit.restriction_factor * config.resistance_gain_restriction


def solve_operating_point(
    circuit: CircuitState,
    config: CircuitConfig,
    base_pressure_bar: float,
    nominal_flow_capacity_cm3_min: float,
    pump_efficiency: float,
) -> CircuitOperatingPoint:
    """Reduced-order solve for one circuit's steady-state pressure/flow demand, given the
    pump's nominal design point. See module docstring for the raw-vs-delivered equations."""
    ratio = resistance_ratio(circuit, config)
    required_pressure = base_pressure_bar * ratio
    raw_flow = max(0.0, (nominal_flow_capacity_cm3_min * pump_efficiency) / ratio)
    delivered_flow = max(0.0, raw_flow * (1.0 - circuit.leakage_factor))
    return CircuitOperatingPoint(
        resistance_ratio=ratio,
        required_pressure_bar=required_pressure,
        raw_flow_cm3_min=raw_flow,
        delivered_flow_cm3_min=delivered_flow,
    )


def circuit_backpressure_bar(
    pump_pressure_bar: float, circuit: CircuitState, config: CircuitConfig
) -> float:
    """Pressure as measured at the circuit (vs. at the pump): a leak bleeds off a small
    share of pump pressure before it reaches the circuit sensor."""
    loss = circuit.leakage_factor * config.leakage_pressure_loss_gain
    return max(0.0, pump_pressure_bar * (1.0 - loss))


def step_natural_variation(
    circuit: CircuitState,
    config: CircuitConfig,
    dt_s: float,
    rng: random.Random,
    *,
    restriction_offset: float = 0.0,
    leakage_offset: float = 0.0,
) -> None:
    """Healthy circuits are not perfectly static (Phase 3 brief §14): mean-reverting random
    walk around the configured demo-healthy defaults, bounded well below anything a rule
    engine would later treat as a developing fault (docs/FAILURE_MODE_CATALOG.md §3).

    `restriction_offset`/`leakage_offset` (Phase 4, docs/SCENARIO_ENGINE.md §5) shift the
    healthy baseline itself — the mean-reversion target — so an active Gradual
    Restriction/Sudden Blockage/Leakage scenario is represented as "the healthy baseline
    has moved," with the same natural micro-variation still layered on top, rather than a
    second, competing control path. Both default to 0.0 (no scenario active — identical to
    Phase 3 behavior).
    """
    baseline_restriction = clip(config.default_restriction_factor + restriction_offset, 0.0, 1.0)
    noise = rng.gauss(0.0, config.restriction_noise_std)
    target = clip(baseline_restriction + noise, 0.0, baseline_restriction + 0.05)
    circuit.restriction_factor = exp_relax(circuit.restriction_factor, target, dt_s, tau_s=180.0)

    circuit.leakage_factor = clip(config.default_leakage_factor + leakage_offset, 0.0, 1.0)
