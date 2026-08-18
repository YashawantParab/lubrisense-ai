from __future__ import annotations

from app.baselines.domain.statistics import compute_robust_statistics


def test_empty_returns_none() -> None:
    assert compute_robust_statistics([]) is None


def test_basic_stats() -> None:
    stats = compute_robust_statistics([10.0, 20.0, 30.0, 40.0, 50.0])
    assert stats is not None
    assert stats.count == 5
    assert stats.median == 30.0
    assert stats.min == 10.0
    assert stats.max == 50.0
    assert stats.mean == 30.0


def test_caution_count_tracked_separately_not_excluded() -> None:
    stats = compute_robust_statistics([10.0, 20.0, 30.0], [False, True, False])
    assert stats is not None
    assert stats.count == 3  # caution samples are still counted, not excluded
    assert stats.caution_count == 1


def test_outlier_does_not_dominate_median() -> None:
    values = [10.0, 11.0, 9.0, 10.5, 9.5, 1000.0]
    stats = compute_robust_statistics(values)
    assert stats is not None
    # Median stays close to the tight cluster despite one huge outlier.
    assert 9.0 <= stats.median <= 11.0
    # Mean, by contrast, gets dragged up substantially.
    assert stats.mean > 150.0


def test_single_value() -> None:
    stats = compute_robust_statistics([42.0])
    assert stats is not None
    assert stats.count == 1
    assert stats.median == 42.0
    assert stats.stddev is None
    assert stats.p05 == stats.p95 == 42.0
