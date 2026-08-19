from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import MetricProvenance


class MetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    data_completeness_note: str | None


class ProductMetricsResponse(BaseModel):
    north_star: MetricResponse
    supporting: list[MetricResponse]
    generated_at: datetime
