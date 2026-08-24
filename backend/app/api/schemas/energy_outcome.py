"""Energy-outcome-verification API contracts, Pass 3
(docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Output is conservative,
evidence-strength language (`energy_outcome_status`, `lubrication_association_status`),
never a "savings" or "verified" claim — see the design doc's claim-hierarchy section."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EnergyOutcomeVerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    maintenance_case_id: uuid.UUID
    incident_id: uuid.UUID | None

    intervention_timestamp: datetime
    pre_window_start: datetime | None
    pre_window_end: datetime | None
    post_window_start: datetime | None
    post_window_end: datetime | None

    pre_mean_actual_power_kw: float | None
    pre_mean_expected_power_kw: float | None
    pre_mean_residual_kw: float | None
    pre_mean_residual_pct: float | None

    post_mean_actual_power_kw: float | None
    post_mean_expected_power_kw: float | None
    post_mean_residual_kw: float | None
    post_mean_residual_pct: float | None

    residual_change_kw: float | None
    residual_change_pct: float | None

    comparability_status: str
    comparison_confidence: str

    energy_outcome_status: str
    estimated_avoided_energy_kwh: float | None
    energy_estimate_status: str

    pre_attribution_id: uuid.UUID | None
    pre_attribution_level: str | None

    condition_outcome_status: str | None

    maintenance_relevant: bool
    lubrication_association_status: str

    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    limiting_factors: list[str]
    alternative_explanations: list[str]

    provenance: dict[str, Any]

    policy_version: str
    created_at: datetime
