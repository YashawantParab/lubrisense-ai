"""Phase 17 maintenance-workflow API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import (
    FeedbackClassification,
    MaintenanceActionType,
    TechnicianFindingResult,
)


class ChecklistItem(BaseModel):
    text: str
    completed: bool


class MaintenanceCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    incident_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    condition_assessment_id: uuid.UUID
    decision_assessment_id: uuid.UUID
    recommended_action: str
    recommended_window: str
    priority: str
    human_review_required: bool
    state: str
    checklist: list[ChecklistItem]
    checklist_template_id: str
    feedback_classification: str | None
    planned_for: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    policy_version: str
    created_at: datetime


class TechnicianFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    maintenance_case_id: uuid.UUID
    result: str
    component: str | None
    observed_issue: str | None
    notes: str
    technician_identifier: str
    recorded_at: datetime


class MaintenanceActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    maintenance_case_id: uuid.UUID
    action_type: str
    notes: str
    recorded_by: str
    recorded_at: datetime


class FeedbackRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    maintenance_case_id: uuid.UUID
    incident_id: uuid.UUID
    condition_assessment_id: uuid.UUID
    decision_assessment_id: uuid.UUID
    classification: str
    confirmed_component: str | None
    confirmed_finding: str | None
    post_action_condition_type: str | None
    notes: str
    recorded_by: str
    recorded_at: datetime


class PlanCaseRequest(BaseModel):
    planned_for: datetime | None = None


class RecordFindingRequest(BaseModel):
    result: TechnicianFindingResult
    component: str | None = None
    observed_issue: str | None = None
    notes: str
    technician_identifier: str = "demo-technician"


class RecordActionRequest(BaseModel):
    action_type: MaintenanceActionType
    notes: str
    recorded_by: str = "demo-technician"


class CompleteCaseRequest(BaseModel):
    classification: FeedbackClassification
    confirmed_component: str | None = None
    confirmed_finding: str | None = None
    notes: str = ""
    recorded_by: str = "demo-technician"


class CancelCaseRequest(BaseModel):
    reason: str = "Cancelled."
