"""Cycle-level baseline (Phase 8 brief §25) — pressure rise time, peak pressure, cycle
duration, completion success rate, derived from persisted `PRESSURE`/`CYCLE_COMPLETION`
telemetry alone, never from the simulator's hidden `CyclePhase` state
(`simulator/simulator/domain/enums.py::CyclePhase`) — the baseline layer "should behave as
if telemetry came from real devices" (Phase 8 brief §6), and a real deployment's telemetry
would not expose an internal controller state machine either.

Cycle boundaries are reconstructed from `PRESSURE` alone: a lubrication cycle
(`docs/SIMULATOR.md` §5 — PUMP_START -> PRESSURE_BUILD -> FLOW_DELIVERY -> COMPLETING) is
visible in `PRESSURE` as a contiguous run of above-idle-threshold readings bounded by
near-zero/idle readings before and after. This is the same idle-threshold heuristic
`app.baselines.strategies.contextual` uses for the `cycle_phase` context bucket
(`ACTIVE`/`IDLE`) — cycle-level baseline is that same segmentation taken one step further,
into whole-cycle aggregates rather than per-reading buckets.
"""

from __future__ import annotations

import statistics as _stats
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

from app.baselines.domain.statistics import MAD_TO_STD_SCALE


@dataclass(frozen=True)
class PressureSample:
    event_id: uuid.UUID
    source_timestamp: datetime
    value: float


@dataclass(frozen=True)
class CompletionSample:
    source_timestamp: datetime
    value: float
    """`CYCLE_COMPLETION` is a boolean sensor (`demo_engineering.yaml`): >= 0.5 is treated
    as a completed-cycle observation."""


@dataclass(frozen=True)
class CycleBaselineStatistics:
    cycle_count: int
    median_duration_seconds: float
    duration_mad: float
    median_peak_pressure: float
    median_rise_time_seconds: float | None
    completion_success_rate: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _segment_cycles(
    pressure: list[PressureSample], idle_threshold: float
) -> list[list[PressureSample]]:
    ordered = sorted(pressure, key=lambda p: p.source_timestamp)
    segments: list[list[PressureSample]] = []
    current: list[PressureSample] = []
    for point in ordered:
        if point.value > idle_threshold:
            current.append(point)
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def compute_cycle_baseline(
    pressure: list[PressureSample],
    completion: list[CompletionSample],
    *,
    idle_threshold: float,
    rise_time_ratio: float = 0.9,
    completion_match_window_seconds: float = 30.0,
) -> CycleBaselineStatistics | None:
    """`pressure`/`completion` must already be quality-gated. Returns `None` if no
    complete above-idle-threshold segment was found (e.g. the machine never ran a cycle in
    the evaluated window)."""
    segments = _segment_cycles(pressure, idle_threshold)
    if not segments:
        return None

    durations: list[float] = []
    peaks: list[float] = []
    rise_times: list[float] = []
    successes = 0

    for segment in segments:
        start = segment[0].source_timestamp
        end = segment[-1].source_timestamp
        duration = (end - start).total_seconds()
        if duration <= 0:
            continue
        durations.append(duration)
        peak = max(p.value for p in segment)
        peaks.append(peak)

        rise_target = peak * rise_time_ratio
        rise_point = next((p for p in segment if p.value >= rise_target), None)
        if rise_point is not None:
            rise_times.append((rise_point.source_timestamp - start).total_seconds())

        if any(
            c.value >= 0.5
            and abs((c.source_timestamp - end).total_seconds()) <= completion_match_window_seconds
            for c in completion
        ):
            successes += 1

    if not durations:
        return None

    median_duration = _stats.median(durations)
    duration_mad = _stats.median([abs(d - median_duration) for d in durations]) * MAD_TO_STD_SCALE

    return CycleBaselineStatistics(
        cycle_count=len(durations),
        median_duration_seconds=median_duration,
        duration_mad=duration_mad,
        median_peak_pressure=_stats.median(peaks),
        median_rise_time_seconds=_stats.median(rise_times) if rise_times else None,
        completion_success_rate=successes / len(durations),
    )
