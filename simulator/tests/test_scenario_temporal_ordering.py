"""Temporal-ordering test for Gradual Restriction (Phase 4 brief §26): lubrication-path
deviation (pressure) must appear measurably before significant bearing degradation
(temperature) — never simultaneously, and never in the wrong order.

Compares a scenario run against a same-seed healthy run (severity_max=0.0) so the "onset"
of a deviation is isolated from ordinary load-driven variation (docs/SIMULATOR.md §9 shows
healthy bearing temperature already swings ~15 degC with load alone, so a bare threshold on
the scenario run in isolation would not reliably isolate the scenario's own contribution).
"""

from __future__ import annotations

from simulator.domain.enums import CyclePhase
from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios import create_instance, load_scenario_definition

_TICKS = 5760  # 24 simulated hours at 15s step
_STEP_SECONDS = 15.0
_PRESSURE_DEVIATION_BAR = 0.5
_TEMPERATURE_DEVIATION_C = 3.0


def _run_series(topology, config, seed, start_time, severity_max):  # type: ignore[no-untyped-def]
    definition = load_scenario_definition("gradual_restriction")
    instance = create_instance(definition, topology, start_seconds=0.0, severity_max=severity_max)
    engine = SimulationEngine(
        topology=topology,
        config=config,
        seed=seed,
        start_time=start_time,
        step_seconds=_STEP_SECONDS,
        scenario_instances=[instance],
    )
    bearing_id = topology.lubrication_system.circuits[0].lubrication_points[0].bearing_id
    pressure_by_tick: dict[int, float] = {}
    temperature_by_tick: dict[int, float] = {}
    for i in range(_TICKS):
        tick = engine.step()
        for r in tick.readings:
            if (
                r.measurement_type == "PRESSURE"
                and r.simulation_state == CyclePhase.FLOW_DELIVERY.value
            ):
                pressure_by_tick[i] = r.true_value
        temperature_by_tick[i] = engine.state.bearings[bearing_id].temperature_c
    return pressure_by_tick, temperature_by_tick


def _first_deviation_tick(
    scenario: dict[int, float], healthy: dict[int, float], threshold: float
) -> int | None:
    for i in sorted(scenario):
        if i in healthy and abs(scenario[i] - healthy[i]) > threshold:
            return i
    return None


def test_pressure_deviation_precedes_bearing_temperature_deviation(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    seed = 31
    healthy_pressure, healthy_temp = _run_series(
        flagship_topology, engineering_config, seed, fixed_start_time, severity_max=0.0
    )
    scenario_pressure, scenario_temp = _run_series(
        flagship_topology, engineering_config, seed, fixed_start_time, severity_max=1.0
    )

    pressure_onset = _first_deviation_tick(
        scenario_pressure, healthy_pressure, _PRESSURE_DEVIATION_BAR
    )
    temperature_onset = _first_deviation_tick(scenario_temp, healthy_temp, _TEMPERATURE_DEVIATION_C)

    assert pressure_onset is not None, "restriction must eventually raise cycle pressure"
    assert (
        temperature_onset is not None
    ), "sustained restriction must eventually raise bearing temperature"

    pressure_onset_seconds = pressure_onset * _STEP_SECONDS
    temperature_onset_seconds = temperature_onset * _STEP_SECONDS
    lead_time_seconds = temperature_onset_seconds - pressure_onset_seconds

    assert lead_time_seconds > 0, (
        f"pressure deviation at t={pressure_onset_seconds}s must precede bearing "
        f"temperature deviation at t={temperature_onset_seconds}s"
    )
    # Require a lead time on the order of the bearing's own thermal lag time constant
    # (600s, demo_engineering.yaml) — not just one lucky tick ahead of the other.
    assert lead_time_seconds >= engineering_config.bearing.temperature_lag_time_constant_s
