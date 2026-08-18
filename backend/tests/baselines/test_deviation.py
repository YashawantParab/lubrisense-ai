from __future__ import annotations

from app.baselines.domain.deviation import compute_deviation, not_enough_data
from app.baselines.domain.statistics import compute_robust_statistics
from app.domain.enums import DeviationClassification


def _stats(center: float = 50.0, spread: float = 2.0):
    values = [center - spread, center - spread / 2, center, center + spread / 2, center + spread]
    stats = compute_robust_statistics(values)
    assert stats is not None
    return stats


def test_not_enough_data() -> None:
    result = not_enough_data()
    assert result.classification == DeviationClassification.NOT_ENOUGH_DATA
    assert result.standardized_distance is None


def test_value_at_median_is_within_expected_range() -> None:
    stats = _stats()
    result = compute_deviation(stats.median, stats, mild_multiplier=2.0, strong_multiplier=4.0)
    assert result.classification == DeviationClassification.WITHIN_EXPECTED_RANGE
    assert result.standardized_distance == 0.0


def test_far_value_is_strong_deviation() -> None:
    stats = _stats()
    result = compute_deviation(
        stats.median + 1000.0, stats, mild_multiplier=2.0, strong_multiplier=4.0
    )
    assert result.classification == DeviationClassification.STRONG_DEVIATION


def test_degenerate_constant_distribution_stays_json_safe() -> None:
    stats = compute_robust_statistics([5.0, 5.0, 5.0, 5.0])
    assert stats is not None
    assert stats.mad == 0.0
    result = compute_deviation(9.0, stats, mild_multiplier=2.0, strong_multiplier=4.0)
    assert result.standardized_distance is not None
    assert result.standardized_distance < float("inf")  # must be JSON-serializable
    assert result.classification == DeviationClassification.STRONG_DEVIATION
