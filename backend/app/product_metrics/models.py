from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import MetricProvenance


@dataclass(frozen=True)
class Metric:
    """One metric with full provenance (Phase 22 brief §22.3) — never presented as a
    bare number. `numerator`/`denominator` are `None` when the metric is not a ratio."""

    metric_id: str
    name: str
    definition: str
    window_description: str
    value: float | None
    unit: str
    numerator: float | None
    denominator: float | None
    provenance: MetricProvenance
    source: str
    scope: str
    calculated_at: datetime
    data_completeness_note: str | None = None


@dataclass(frozen=True)
class NorthStarResult:
    metric: Metric
    meaningful_issues_detected_with_lead_time: int
    meaningful_issues_total: int


@dataclass(frozen=True)
class ProductMetricsResult:
    north_star: Metric
    supporting: list[Metric]
    generated_at: datetime
