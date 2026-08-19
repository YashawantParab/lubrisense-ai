from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.baselines.domain.cycle_metrics import (
    CompletionSample,
    PressureSample,
    compute_cycle_baseline,
)


def _ts(seconds: float) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds)


def _pressure(seconds: float, value: float) -> PressureSample:
    return PressureSample(event_id=uuid.uuid4(), source_timestamp=_ts(seconds), value=value)


def test_none_when_no_cycles() -> None:
    idle = [_pressure(s, 0.1) for s in range(10)]
    assert compute_cycle_baseline(idle, [], idle_threshold=0.5) is None


def test_single_cycle_shape() -> None:
    # Duration/peak/rise-time are measured across the above-idle-threshold points only
    # (0.1-valued readings at t=0/t=25 are IDLE, not part of the segment).
    pressure = [
        _pressure(0, 0.1),
        _pressure(5, 2.0),
        _pressure(10, 6.0),
        _pressure(15, 9.0),  # peak
        _pressure(20, 5.0),
        _pressure(25, 0.1),
    ]
    completion = [CompletionSample(source_timestamp=_ts(25), value=1.0)]
    result = compute_cycle_baseline(pressure, completion, idle_threshold=0.5)
    assert result is not None
    assert result.cycle_count == 1
    assert result.median_peak_pressure == 9.0
    assert result.completion_success_rate == 1.0
    assert result.median_duration_seconds == 15.0  # t=5 (first above-threshold) to t=20


def test_incomplete_cycle_lowers_success_rate() -> None:
    cycle_a = [_pressure(0, 0.1), _pressure(5, 8.0), _pressure(8, 7.0), _pressure(10, 0.1)]
    cycle_b = [_pressure(100, 0.1), _pressure(105, 8.0), _pressure(108, 7.0), _pressure(110, 0.1)]
    completion = [CompletionSample(source_timestamp=_ts(8), value=1.0)]  # only cycle_a confirmed
    result = compute_cycle_baseline(cycle_a + cycle_b, completion, idle_threshold=0.5)
    assert result is not None
    assert result.cycle_count == 2
    assert result.completion_success_rate == 0.5


def test_completion_success_rate_is_none_without_a_completion_signal() -> None:
    # A topology with no `CYCLE_COMPLETION` sensor at all must not be reported as a
    # confirmed 0% success rate — that would misrepresent "no signal" as "observed
    # failure" and would make `check_cycle_completion_failure` fire permanently for any
    # machine that simply lacks the sensor.
    pressure = [_pressure(0, 0.1), _pressure(5, 8.0), _pressure(8, 7.0), _pressure(10, 0.1)]
    result = compute_cycle_baseline(pressure, [], idle_threshold=0.5)
    assert result is not None
    assert result.cycle_count == 1
    assert result.completion_success_rate is None
