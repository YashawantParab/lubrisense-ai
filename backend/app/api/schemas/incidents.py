"""Phase 16 incident-management API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    correlation_key: str
    incident_type: str
    title: str
    summary: str
    severity: str
    priority: str
    state: str
    first_detected_at: datetime
    last_updated_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    condition_assessment_ids: list[str]
    decision_assessment_ids: list[str]
    prognostic_assessment_ids: list[str]
    rule_finding_ids: list[str]
    ml_result_ids: list[str]
    state_estimate_ids: list[str]
    evidence_refs: dict[str, object]
    assigned_to: str | None
    policy_version: str
    engine_version: str
    created_at: datetime


class IncidentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    event_type: str
    summary: str
    details: dict[str, object]
    recorded_at: datetime


class IncidentReasonRequest(BaseModel):
    reason: str = "Manual action."
