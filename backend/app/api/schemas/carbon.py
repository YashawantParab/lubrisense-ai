"""Carbon-intelligence API contracts, Pass 4 (docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md,
ADR-176). Output is an operational estimate with explicit provenance, never "carbon
saved"/"certified reduction" language — see the design doc's claim-terminology section."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import EmissionFactorMethod, MetricProvenance


class SiteEmissionFactorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID

    factor_type: str
    factor_value: float
    factor_unit: str
    method: str

    source_name: str
    source_reference: str | None
    jurisdiction: str | None

    effective_from: datetime
    effective_to: datetime | None
    published_at: datetime | None
    is_active: bool

    provenance: str

    created_at: datetime


class ConfigureEmissionFactorRequest(BaseModel):
    factor_value: float = Field(gt=0)
    source_name: str
    source_reference: str | None = None
    jurisdiction: str | None = None
    provenance: MetricProvenance = MetricProvenance.DEMO_ESTIMATE
    method: EmissionFactorMethod = EmissionFactorMethod.LOCATION_BASED


class CarbonImpactEstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    machine_id: uuid.UUID
    energy_outcome_verification_id: uuid.UUID
    emission_factor_id: uuid.UUID | None

    observed_period_start: datetime | None
    observed_period_end: datetime | None

    qualified_avoided_energy_kwh: float | None

    emission_factor_value: float | None
    emission_factor_unit: str | None
    method: str | None

    estimated_co2e_kg: float | None
    estimate_status: str

    limitations: list[str]
    provenance: dict[str, Any]

    policy_version: str
    created_at: datetime
