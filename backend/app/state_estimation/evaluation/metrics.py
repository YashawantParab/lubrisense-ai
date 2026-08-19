"""Pure evaluation metric functions (Phase 12 brief §29) — every function here takes two
aligned numeric series and returns a number. No simulator import, no ground-truth field
name, no I/O: this module has no way to violate the ground-truth boundary (Phase 12 brief
§1) because it never reads anything, it only computes over numbers a caller already
produced. The caller that aligns an estimated-state series against a simulator hidden-state
proxy series lives entirely outside `app.state_estimation` — see
`backend/scripts/evaluate_state_estimation.py` and docs/STATE_ESTIMATION.md "Evaluation
methodology" for why that split is drawn exactly there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def mean_absolute_error(estimated: list[float], truth: list[float]) -> float:
    if len(estimated) != len(truth):
        raise ValueError("series must be the same length")
    if not estimated:
        raise ValueError("series must be non-empty")
    return sum(abs(e - t) for e, t in zip(estimated, truth, strict=True)) / len(estimated)


def root_mean_squared_error(estimated: list[float], truth: list[float]) -> float:
    if len(estimated) != len(truth):
        raise ValueError("series must be the same length")
    if not estimated:
        raise ValueError("series must be non-empty")
    return math.sqrt(
        sum((e - t) ** 2 for e, t in zip(estimated, truth, strict=True)) / len(estimated)
    )


def pearson_correlation(estimated: list[float], truth: list[float]) -> float | None:
    """`None` when either series has zero variance (correlation is undefined, not zero —
    e.g. a perfectly flat HEALTHY-run truth series)."""
    if len(estimated) != len(truth):
        raise ValueError("series must be the same length")
    n = len(estimated)
    if n < 2:
        return None
    mean_e = sum(estimated) / n
    mean_t = sum(truth) / n
    cov = sum((e - mean_e) * (t - mean_t) for e, t in zip(estimated, truth, strict=True))
    var_e = sum((e - mean_e) ** 2 for e in estimated)
    var_t = sum((t - mean_t) ** 2 for t in truth)
    if var_e <= 0 or var_t <= 0:
        return None
    return cov / math.sqrt(var_e * var_t)


def trend_agreement_rate(estimated_trend: list[str], truth_direction: list[str]) -> float:
    """Fraction of ticks where the estimator's reported trend
    (`IMPROVING`/`STABLE`/`DETERIORATING`/`UNKNOWN`) agrees with a caller-derived
    ground-truth direction over the same alphabet. `UNKNOWN` never counts as agreement
    (an estimator declining to claim a direction is not the same as being right)."""
    if len(estimated_trend) != len(truth_direction):
        raise ValueError("series must be the same length")
    if not estimated_trend:
        raise ValueError("series must be non-empty")
    agreements = sum(
        1
        for e, t in zip(estimated_trend, truth_direction, strict=True)
        if e != "UNKNOWN" and e == t
    )
    return agreements / len(estimated_trend)


def smoothness(estimated: list[float]) -> float:
    """Mean absolute tick-to-tick change in the estimated level — a low value means the
    state evolves smoothly rather than jumping wildly on individual noisy observations
    (Phase 12 brief §20). Not normalized against anything external; only meaningful as a
    relative comparison (e.g. a HEALTHY run's smoothness vs. a fault run's)."""
    if len(estimated) < 2:
        raise ValueError("series must have at least two points")
    diffs = [abs(b - a) for a, b in zip(estimated, estimated[1:], strict=False)]
    return sum(diffs) / len(diffs)


@dataclass(frozen=True, slots=True)
class LeadLagResult:
    """Positive `lead_seconds` means the estimator crossed `threshold` before the
    ground-truth proxy did (an early warning); negative means it lagged."""

    lead_seconds: float | None
    estimator_crossing_index: int | None
    truth_crossing_index: int | None


def detection_lead_lag(
    estimated: list[float],
    truth: list[float],
    timestamps_seconds: list[float],
    threshold: float,
) -> LeadLagResult:
    if not (len(estimated) == len(truth) == len(timestamps_seconds)):
        raise ValueError("series must be the same length")
    est_idx = next((i for i, v in enumerate(estimated) if v >= threshold), None)
    truth_idx = next((i for i, v in enumerate(truth) if v >= threshold), None)
    if est_idx is None or truth_idx is None:
        return LeadLagResult(None, est_idx, truth_idx)
    lead = timestamps_seconds[truth_idx] - timestamps_seconds[est_idx]
    return LeadLagResult(lead, est_idx, truth_idx)
