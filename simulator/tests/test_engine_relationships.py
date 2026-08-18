"""Engine-level (integration) relationship checks against the real flagship topology.

Per-equation relationship checks (restriction -> flow, pump efficiency -> delivery,
lubrication_effectiveness -> bearing condition) already have direct, isolated unit tests in
test_circuit.py / test_pump.py / test_bearing.py (Phase 3 brief §23). This module proves the
same relationships still hold once everything is wired together through the real
`SimulationEngine` against the seeded flagship machine, not just in isolated physics calls.
"""

from __future__ import annotations

import statistics

from simulator.domain.enums import OperatingState
from simulator.engine.simulation_engine import SimulationEngine


def test_higher_load_correlates_with_higher_bearing_temperature(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=11,
        start_time=fixed_start_time,
        step_seconds=5.0,
    )

    samples: list[tuple[float, float]] = []  # (load_percent, mean bearing temperature)
    for _ in range(7200):  # 10 simulated hours, crosses the configured shift window
        engine.step()
        machine = engine.state.machine
        if machine.operating_state.is_running:
            temps = [b.temperature_c for b in engine.state.bearings.values()]
            samples.append((machine.load_percent, statistics.mean(temps)))

    assert len(samples) > 100, "run must include a meaningful amount of RUNNING time"
    samples.sort(key=lambda s: s[0])
    low_quartile = samples[: len(samples) // 4]
    high_quartile = samples[-len(samples) // 4 :]
    low_mean_temp = statistics.mean(t for _, t in low_quartile)
    high_mean_temp = statistics.mean(t for _, t in high_quartile)
    assert high_mean_temp > low_mean_temp


def test_rpm_only_nonzero_while_running(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=12,
        start_time=fixed_start_time,
        step_seconds=5.0,
    )
    for _ in range(7200):
        engine.step()
        machine = engine.state.machine
        if machine.operating_state == OperatingState.STOPPED:
            assert machine.rpm == 0.0
        elif machine.operating_state.is_running:
            assert machine.rpm > 0.0
