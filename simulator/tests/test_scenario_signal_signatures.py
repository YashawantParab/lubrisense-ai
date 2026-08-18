"""Signal-direction ("relationship") tests for each scenario type (Phase 4 brief §25).

These test *trends*, never one exact magic value — e.g. "pressure in the second half of the
run is higher than the first half," not "pressure equals 14.3 bar at t=7200s."
"""

from __future__ import annotations

import statistics

from simulator.domain.enums import CyclePhase
from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios import create_instance, load_scenario_definition


def _run(topology, config, seed, start_time, scenario_name, ticks, step_seconds, **overrides):  # type: ignore[no-untyped-def]
    definition = load_scenario_definition(scenario_name)
    instance = create_instance(definition, topology, start_seconds=0.0, **overrides)
    engine = SimulationEngine(
        topology=topology,
        config=config,
        seed=seed,
        start_time=start_time,
        step_seconds=step_seconds,
        scenario_instances=[instance],
    )
    readings = []
    ground_truth = []
    for _ in range(ticks):
        tick = engine.step()
        readings.extend(tick.readings)
        ground_truth.append(tick.ground_truth)
    return readings, ground_truth, instance


def _halves(values: list[float]) -> tuple[list[float], list[float]]:
    mid = len(values) // 2
    return values[:mid], values[mid:]


def test_gradual_restriction_raises_flow_delivery_pressure_over_time(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    readings, ground_truth, instance = _run(
        flagship_topology,
        engineering_config,
        seed=21,
        start_time=fixed_start_time,
        scenario_name="gradual_restriction",
        ticks=5760,  # 24 simulated hours at 15s step
        step_seconds=15.0,
        severity_max=1.0,
    )
    assert instance.severity > 0.05, "scenario must have actually progressed during the run"

    pressures = [
        r.true_value
        for r in readings
        if r.measurement_type == "PRESSURE" and r.simulation_state == CyclePhase.FLOW_DELIVERY.value
    ]
    assert len(pressures) > 20
    first_half, second_half = _halves(pressures)
    assert statistics.mean(second_half) > statistics.mean(first_half)

    restrictions = [gt.circuits[0].restriction_factor for gt in ground_truth]
    first_half_r, second_half_r = _halves(restrictions)
    assert statistics.mean(second_half_r) > statistics.mean(first_half_r)


def test_pump_degradation_lowers_efficiency_over_time(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    _readings, ground_truth, instance = _run(
        flagship_topology,
        engineering_config,
        seed=22,
        start_time=fixed_start_time,
        scenario_name="pump_degradation",
        ticks=5760,
        step_seconds=15.0,
        severity_max=1.0,
    )
    assert instance.severity > 0.01
    efficiencies = [gt.pump_efficiency for gt in ground_truth if gt.pump_efficiency is not None]
    first_half, second_half = _halves(efficiencies)
    assert statistics.mean(second_half) < statistics.mean(first_half)


def test_leakage_reduces_bearing_lubrication_effectiveness_without_raising_pressure(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    """Distinguishing leakage from restriction (Phase 4 brief §8, §27): both reduce
    delivered/useful lubrication, but leakage does so *without* raising required pressure
    (docs/SCENARIO_ENGINE.md §5 — leakage only affects the raw-vs-delivered flow split, not
    resistance_ratio), while restriction raises pressure as its primary signature."""
    readings, ground_truth, instance = _run(
        flagship_topology,
        engineering_config,
        seed=23,
        start_time=fixed_start_time,
        scenario_name="leakage",
        ticks=5760,
        step_seconds=15.0,
        severity_max=1.0,
    )
    assert instance.severity > 0.1

    served_bearing_id = (
        flagship_topology.lubrication_system.circuits[0].lubrication_points[0].bearing_id
    )
    effectiveness = [
        next(b.lubrication_effectiveness for b in gt.bearings if b.bearing_id == served_bearing_id)
        for gt in ground_truth
    ]
    first_half, second_half = _halves(effectiveness)
    assert statistics.mean(second_half) < statistics.mean(first_half)

    pressures = [
        r.true_value
        for r in readings
        if r.measurement_type == "PRESSURE" and r.simulation_state == CyclePhase.FLOW_DELIVERY.value
    ]
    first_p, second_p = _halves(pressures)
    # required pressure is governed by restriction only (unaffected by leakage) — allow
    # noise but no *systematic* rise the way restriction produces.
    assert statistics.mean(second_p) < statistics.mean(first_p) * 1.15


def test_over_lubrication_depletes_reservoir_faster_than_healthy_baseline(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    _healthy_readings, healthy_gt, _ = _run(
        flagship_topology,
        engineering_config,
        seed=24,
        start_time=fixed_start_time,
        scenario_name="over_lubrication",
        ticks=5760,
        step_seconds=15.0,
        severity_max=0.0,  # effectively healthy (zero severity ceiling)
    )
    _over_readings, over_gt, instance = _run(
        flagship_topology,
        engineering_config,
        seed=24,
        start_time=fixed_start_time,
        scenario_name="over_lubrication",
        ticks=5760,
        step_seconds=15.0,
        severity_max=1.0,
    )
    assert instance.severity > 0.1
    healthy_final = healthy_gt[-1].reservoir_quantity_l
    over_final = over_gt[-1].reservoir_quantity_l
    assert over_final < healthy_final


def test_independent_bearing_fault_raises_vibration_while_lubrication_path_stays_healthy(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    """The critical distinction from a lubrication-caused fault (Phase 4 brief §15,
    docs/FAILURE_MODE_CATALOG.md §12): vibration rises while pressure, reservoir level, and
    lubrication_effectiveness remain broadly flat/healthy."""
    readings, ground_truth, instance = _run(
        flagship_topology,
        engineering_config,
        seed=25,
        start_time=fixed_start_time,
        scenario_name="independent_bearing_fault",
        ticks=5760,
        step_seconds=15.0,
        severity_max=1.0,
    )
    assert instance.severity > 0.05

    target_bearing_id = instance.target_id
    vibration = [
        r.true_value
        for r in readings
        if r.measurement_type == "VIBRATION_RMS" and r.component_id == target_bearing_id
    ]
    first_half, second_half = _halves(vibration)
    assert statistics.mean(second_half) > statistics.mean(first_half)

    # Lubrication-path signals: no scenario-driven trend.
    effectiveness = [
        next(b.lubrication_effectiveness for b in gt.bearings if b.bearing_id == target_bearing_id)
        for gt in ground_truth
    ]
    assert min(effectiveness) >= 0.9  # never meaningfully starved — this fault never touches it

    restriction_values = [gt.circuits[0].restriction_factor for gt in ground_truth]
    assert max(restriction_values) < 0.1  # stays near the healthy natural-variation band
