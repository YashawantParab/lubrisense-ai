"""Robust descriptive statistics for a numeric sample set (Phase 8 brief §12/§13).

Median/MAD/quantiles are used throughout rather than only mean/stddev, since a skewed or
outlier-contaminated distribution (a handful of transient spikes, a brief sensor hiccup)
should not dominate a robust summary the way it would a plain mean — brief §13's explicit
requirement. Mean/stddev are still computed and stored (useful for `LOAD`/`RPM`-style
roughly-symmetric signals and for the simple z-like distance in `deviation.py`), just never
relied on alone.
"""

from __future__ import annotations

import statistics as _stats
from dataclasses import asdict, dataclass

# Constant that makes MAD a consistent estimator of the standard deviation under a normal
# distribution (1 / Phi^-1(3/4)) — the standard scaling factor, used so MAD-based distance
# in deviation.py is comparable in magnitude to a stddev-based one.
MAD_TO_STD_SCALE = 1.4826


@dataclass(frozen=True)
class RobustStatistics:
    count: int
    caution_count: int
    mean: float
    stddev: float | None
    median: float
    mad: float
    p05: float
    p25: float
    p75: float
    p95: float
    min: float
    max: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation quantile (matches `statistics.quantiles`' `inclusive` method
    at the boundaries without requiring `n>=2` — small samples are common while a baseline
    is still `BUILDING`)."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def compute_robust_statistics(
    values: list[float], caution_flags: list[bool] | None = None
) -> RobustStatistics | None:
    """`None` if `values` is empty — callers must treat that as "no statistics yet", not
    as a zero-filled result. `caution_flags`, if given, must be the same length as
    `values`; every value is still used in every statistic (brief §5's "include, track
    separately" policy — see `TelemetrySample.caution` docstring), only the count differs."""
    if not values:
        return None
    caution_flags = caution_flags or [False] * len(values)
    ordered = sorted(values)
    mean = _stats.fmean(values)
    stddev = _stats.pstdev(values) if len(values) > 1 else None
    median = _stats.median(ordered)
    mad = _stats.median([abs(v - median) for v in values]) * MAD_TO_STD_SCALE
    return RobustStatistics(
        count=len(values),
        caution_count=sum(1 for c in caution_flags if c),
        mean=mean,
        stddev=stddev,
        median=median,
        mad=mad,
        p05=_quantile(ordered, 0.05),
        p25=_quantile(ordered, 0.25),
        p75=_quantile(ordered, 0.75),
        p95=_quantile(ordered, 0.95),
        min=ordered[0],
        max=ordered[-1],
    )
