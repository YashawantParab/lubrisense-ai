"""Wires quality-gated `RESERVOIR_LEVEL` telemetry into `app.baselines.domain.reservoir_trend`
(Phase 8 brief §24). A thin adapter, kept separate from the pure trend math so the engine
only ever imports strategy modules, matching `app.data_quality.services.quality_engine`'s
own rules-vs-orchestration separation.
"""

from __future__ import annotations

from app.baselines.domain.context import TelemetrySample
from app.baselines.domain.reservoir_trend import ReservoirTrendStatistics, compute_reservoir_trend


def compute_reservoir_baseline(samples: list[TelemetrySample]) -> ReservoirTrendStatistics | None:
    usable = sorted((s for s in samples if s.value is not None), key=lambda s: s.source_timestamp)
    points = [(s.source_timestamp, s.value) for s in usable if s.value is not None]
    return compute_reservoir_trend(points)
