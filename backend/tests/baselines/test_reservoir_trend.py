from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.baselines.domain.reservoir_trend import compute_reservoir_trend


def _ts(hours: float) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hours)


def test_none_with_too_few_points() -> None:
    assert compute_reservoir_trend([(_ts(0), 90.0)]) is None


def test_steady_depletion_rate() -> None:
    # Depletes 2%/hour for 10 hours, no refill.
    points = [(_ts(h), 100.0 - 2.0 * h) for h in range(11)]
    result = compute_reservoir_trend(points)
    assert result is not None
    assert result.refill_event_count == 0
    assert result.run_count == 1
    assert abs(result.median_depletion_rate_percent_per_hour - 2.0) < 0.01


def test_refill_detected_and_splits_runs() -> None:
    points = [
        (_ts(0), 90.0),
        (_ts(1), 85.0),
        (_ts(2), 80.0),
        (_ts(3), 95.0),  # refill jump
        (_ts(4), 90.0),
        (_ts(5), 85.0),
    ]
    result = compute_reservoir_trend(points)
    assert result is not None
    assert result.refill_event_count == 1
    assert result.run_count == 2
    assert result.median_depletion_rate_percent_per_hour > 0
