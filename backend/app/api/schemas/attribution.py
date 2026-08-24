"""Lubrication-energy attribution API contracts, Pass 2
(docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Output is evidence-strength
language (`attribution_level`), never a diagnosis, decision, or numeric causal
percentage — see the design doc's product-definition section."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    energy_assessment_id: uuid.UUID
    as_of_timestamp: datetime

    attribution_level: str

    energy_residual_kw: float | None
    energy_residual_pct: float | None

    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    limiting_factors: list[str]
    alternative_explanations: list[str]

    data_quality_state: str
    condition_assessment_id: uuid.UUID | None

    policy_version: str
    created_at: datetime
