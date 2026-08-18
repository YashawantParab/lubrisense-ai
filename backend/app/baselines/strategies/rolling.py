"""ROLLING_ASSET_BASELINE (Phase 8 brief §3) — sensor-level, unsegmented: learns from
recent trusted telemetry for one sensor, with no context split. Every numeric sensor gets
one of these (`context_key=""`) regardless of whether it also gets a
CONTEXTUAL_ASSET_BASELINE — it is the fallback rung between an exact/coarser context match
and the STATIC_ENGINEERING_REFERENCE (`app.baselines.services.fallback`).
"""

from __future__ import annotations

from app.baselines.domain.context import TelemetrySample
from app.baselines.domain.statistics import RobustStatistics, compute_robust_statistics


def compute_rolling_baseline(samples: list[TelemetrySample]) -> RobustStatistics | None:
    usable = [s for s in samples if s.value is not None]
    if not usable:
        return None
    return compute_robust_statistics(
        [s.value for s in usable if s.value is not None], [s.caution for s in usable]
    )
