"""Reservoir-level baseline — directional/trending, not a symmetric range (Phase 8 brief
§24). `RESERVOIR_LEVEL` only ever decreases via delivered lubricant volume and jumps back
up on a refill (`simulator/simulator/physics/reservoir.py`, `docs/SCENARIO_ENGINE.md`'s
standalone refill mechanism) — a plain mean/stddev/percentile band over raw level values
would conflate "normal for a reservoir that was just refilled" with "normal right before
its next scheduled refill", which are opposite ends of the same healthy cycle. Instead this
computes the *rate* of depletion within each run between refills, which is the stable,
comparable quantity.
"""

from __future__ import annotations

import statistics as _stats
from dataclasses import asdict, dataclass
from datetime import datetime

from app.baselines.domain.statistics import MAD_TO_STD_SCALE

# A level increase of at least this many percentage points between consecutive eligible
# readings is treated as a refill event, not sensor noise — demo_engineering.yaml's own
# RESERVOIR_LEVEL sensor noise_std (0.3) + bias_std (0.2) never plausibly produces a jump
# this large from noise alone.
_REFILL_JUMP_THRESHOLD_PERCENT = 3.0


@dataclass(frozen=True)
class ReservoirTrendStatistics:
    sample_count: int
    run_count: int
    refill_event_count: int
    median_depletion_rate_percent_per_hour: float
    depletion_rate_mad: float
    median_run_duration_hours: float | None

    def to_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def compute_reservoir_trend(
    points: list[tuple[datetime, float]],
) -> ReservoirTrendStatistics | None:
    """`points` must already be quality-gated and sorted ascending by timestamp. Splits
    into "runs" (a maximal stretch between refill jumps), computes each run's depletion
    rate via a simple two-point (first, last) slope — deliberately not a full linear
    regression, since Phase 3's delivered-volume-driven depletion is already close to
    piecewise-linear within a run and a two-point slope is simpler to explain and test.
    Returns `None` if fewer than 2 points, or if every run has fewer than 2 points (no
    rate can be computed at all)."""
    if len(points) < 2:
        return None

    runs: list[list[tuple[datetime, float]]] = [[points[0]]]
    refill_event_count = 0
    for previous, current in zip(points, points[1:], strict=False):
        if current[1] - previous[1] >= _REFILL_JUMP_THRESHOLD_PERCENT:
            refill_event_count += 1
            runs.append([current])
        else:
            runs[-1].append(current)

    rates_per_hour: list[float] = []
    durations_hours: list[float] = []
    for run in runs:
        if len(run) < 2:
            continue
        start_ts, start_level = run[0]
        end_ts, end_level = run[-1]
        duration_hours = (end_ts - start_ts).total_seconds() / 3600.0
        if duration_hours <= 0:
            continue
        # Depletion rate reported as a positive percent/hour magnitude — level is
        # non-increasing within a run, so (start - end) >= 0 in the healthy case.
        rates_per_hour.append((start_level - end_level) / duration_hours)
        durations_hours.append(duration_hours)

    if not rates_per_hour:
        return None

    median_rate = _stats.median(rates_per_hour)
    mad = _stats.median([abs(r - median_rate) for r in rates_per_hour]) * MAD_TO_STD_SCALE
    median_duration = _stats.median(durations_hours) if durations_hours else None

    return ReservoirTrendStatistics(
        sample_count=len(points),
        run_count=len(runs),
        refill_event_count=refill_event_count,
        median_depletion_rate_percent_per_hour=median_rate,
        depletion_rate_mad=mad,
        median_run_duration_hours=median_duration,
    )
