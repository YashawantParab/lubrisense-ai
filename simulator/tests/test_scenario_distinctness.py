"""Failure-distinctness validation (Phase 4 brief §27): major failure modes must not
produce trivially-identical signatures under different labels. The goal is not perfect
separability — just proof that swapping one scenario for another actually changes the
observable/ground-truth signature in some dimension.
"""

from __future__ import annotations

import statistics

from simulator.domain.enums import CyclePhase
from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios import create_instance, load_scenario_definition

_TICKS = 3840  # 16 simulated hours at 15s step
_STEP_SECONDS = 15.0


def _signature(topology, config, seed, start_time, scenario_name):  # type: ignore[no-untyped-def]
    definition = load_scenario_definition(scenario_name)
    instance = create_instance(definition, topology, start_seconds=0.0, severity_max=1.0)
    engine = SimulationEngine(
        topology=topology,
        config=config,
        seed=seed,
        start_time=start_time,
        step_seconds=_STEP_SECONDS,
        scenario_instances=[instance],
    )
    pressures = []
    vibrations = []
    missing_count = 0
    for _ in range(_TICKS):
        tick = engine.step()
        for r in tick.readings:
            if (
                r.measurement_type == "PRESSURE"
                and r.simulation_state == CyclePhase.FLOW_DELIVERY.value
            ):
                pressures.append(r.true_value)
            if r.measurement_type == "VIBRATION_RMS":
                vibrations.append(r.true_value)
            if r.observed_value is None:
                missing_count += 1

    bearing_id = topology.lubrication_system.circuits[0].lubrication_points[0].bearing_id
    final_bearing = engine.state.bearings[bearing_id]
    return {
        "mean_pressure": statistics.mean(pressures) if pressures else 0.0,
        "mean_vibration": statistics.mean(vibrations) if vibrations else 0.0,
        "final_lubrication_effectiveness": final_bearing.lubrication_effectiveness,
        "final_health": final_bearing.health,
        "final_reservoir_l": engine.state.lubrication_system.reservoir.quantity_l,
        "final_pump_efficiency": engine.state.lubrication_system.pump.efficiency,
        "missing_observation_count": missing_count,
    }


def _assert_distinct(
    sig_a: dict[str, float], sig_b: dict[str, float], *, rel_tol: float = 0.02
) -> None:
    differing_dimensions = [
        key
        for key in sig_a
        if abs(sig_a[key] - sig_b[key]) > rel_tol * (abs(sig_a[key]) + abs(sig_b[key]) + 1e-9)
    ]
    assert differing_dimensions, f"signatures are trivially identical: {sig_a} vs {sig_b}"


def test_restriction_vs_leakage_are_distinct(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    restriction = _signature(
        flagship_topology, engineering_config, 41, fixed_start_time, "gradual_restriction"
    )
    leakage = _signature(flagship_topology, engineering_config, 41, fixed_start_time, "leakage")
    _assert_distinct(restriction, leakage)
    # The specific, physically-grounded distinction (docs/SCENARIO_ENGINE.md §5): leakage
    # does not raise required pressure the way restriction does.
    assert leakage["mean_pressure"] < restriction["mean_pressure"]


def test_restriction_vs_pump_degradation_are_distinct(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    restriction = _signature(
        flagship_topology, engineering_config, 42, fixed_start_time, "gradual_restriction"
    )
    pump_degradation = _signature(
        flagship_topology, engineering_config, 42, fixed_start_time, "pump_degradation"
    )
    _assert_distinct(restriction, pump_degradation)


def test_lubrication_fault_vs_independent_bearing_fault_are_distinct(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    restriction = _signature(
        flagship_topology, engineering_config, 43, fixed_start_time, "gradual_restriction"
    )
    independent = _signature(
        flagship_topology, engineering_config, 43, fixed_start_time, "independent_bearing_fault"
    )
    _assert_distinct(restriction, independent)
    # The specific distinction docs/FAILURE_MODE_CATALOG.md §12 exists to make: the
    # independent fault leaves lubrication_effectiveness untouched while restriction erodes
    # it.
    assert (
        independent["final_lubrication_effectiveness"]
        > restriction["final_lubrication_effectiveness"]
    )


def test_sensor_fault_vs_physical_fault_are_distinct(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    sensor_dropout = _signature(
        flagship_topology, engineering_config, 44, fixed_start_time, "sensor_dropout"
    )
    restriction = _signature(
        flagship_topology, engineering_config, 44, fixed_start_time, "gradual_restriction"
    )
    _assert_distinct(sensor_dropout, restriction)
    # A sensor fault must never itself move the physical state.
    assert sensor_dropout["final_lubrication_effectiveness"] >= 0.95
    assert sensor_dropout["missing_observation_count"] > 0
    assert restriction["missing_observation_count"] == 0
