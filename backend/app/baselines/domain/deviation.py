"""Explainable deviation helper (Phase 8 brief §23) — how far a value sits from a resolved
baseline, expressed as a robust standardized distance plus a coarse three-way
classification. This is explicitly NOT fault/anomaly classification: no severity, no
"faulty" label, no recommendation — just a distance and a bucket a later rules/ML/
condition-intelligence phase can build on.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.baselines.domain.statistics import RobustStatistics
from app.domain.enums import DeviationClassification


@dataclass(frozen=True)
class DeviationResult:
    classification: DeviationClassification
    standardized_distance: float | None
    quantile_position: float | None
    """Where `value` sits relative to `[p05, p95]`, expressed as a fraction (0.0 at p05,
    1.0 at p95, can exceed [0, 1] outside that band) — a second, distribution-shape-aware
    view of the same distance, alongside the MAD-standardized one."""
    method: str


def not_enough_data() -> DeviationResult:
    return DeviationResult(
        classification=DeviationClassification.NOT_ENOUGH_DATA,
        standardized_distance=None,
        quantile_position=None,
        method="none",
    )


def compute_deviation(
    value: float,
    stats: RobustStatistics,
    *,
    mild_multiplier: float,
    strong_multiplier: float,
) -> DeviationResult:
    """Robust (median/MAD) standardized distance when the distribution has any spread;
    falls back to a plain quantile-position check when `mad == 0` (e.g. a boolean/constant
    signal like `CYCLE_COMPLETION`, where MAD-division would be undefined) — `method`
    records which path was used so a caller/API response never has to guess."""
    if stats.mad > 0:
        distance = abs(value - stats.median) / stats.mad
        method = "robust_mad"
    elif stats.stddev:
        distance = abs(value - stats.mean) / stats.stddev
        method = "stddev_fallback"
    else:
        # A large finite sentinel, not `float("inf")` — `inf` is not valid JSON and this
        # value is returned directly through the API (`standardized_distance`).
        distance = 0.0 if value == stats.median else 1e9
        method = "degenerate_constant"

    span = stats.p95 - stats.p05
    quantile_position = (value - stats.p05) / span if span > 0 else None

    if distance <= mild_multiplier:
        classification = DeviationClassification.WITHIN_EXPECTED_RANGE
    elif distance <= strong_multiplier:
        classification = DeviationClassification.MILD_DEVIATION
    else:
        classification = DeviationClassification.STRONG_DEVIATION

    return DeviationResult(
        classification=classification,
        standardized_distance=distance,
        quantile_position=quantile_position,
        method=method,
    )
