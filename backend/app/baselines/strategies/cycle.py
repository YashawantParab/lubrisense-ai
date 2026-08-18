"""Wires quality-gated `PRESSURE`/`CYCLE_COMPLETION` telemetry for one machine into
`app.baselines.domain.cycle_metrics` (Phase 8 brief §25). Machine-scoped, not sensor-scoped
— a lubrication cycle is a property of the whole lubrication system's pump/circuit, not a
single sensor, matching how `app.data_quality.services.window_evaluator` scopes
communication-loss checks to a machine rather than a sensor.
"""

from __future__ import annotations

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.context import TelemetrySample
from app.baselines.domain.cycle_metrics import (
    CompletionSample,
    CycleBaselineStatistics,
    PressureSample,
    compute_cycle_baseline,
)


def compute_machine_cycle_baseline(
    pressure_samples: list[TelemetrySample],
    completion_samples: list[TelemetrySample],
    policy: BaselinePolicy,
) -> CycleBaselineStatistics | None:
    idle_threshold = policy.cycle_phase_idle_threshold_for("PRESSURE")
    if idle_threshold is None:
        return None
    pressure = [
        PressureSample(event_id=s.event_id, source_timestamp=s.source_timestamp, value=s.value)
        for s in pressure_samples
        if s.value is not None
    ]
    completion = [
        CompletionSample(source_timestamp=s.source_timestamp, value=s.value)
        for s in completion_samples
        if s.value is not None
    ]
    return compute_cycle_baseline(pressure, completion, idle_threshold=idle_threshold)
