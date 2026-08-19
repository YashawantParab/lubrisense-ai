"""Phase 14 decision-intelligence API contracts. Every physical action requires human
review; nothing here operates machinery — see docs/DECISION_INTELLIGENCE.md "Purpose"."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DecisionAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    condition_assessment_id: uuid.UUID
    prognostic_assessment_id: uuid.UUID | None
    priority: str
    recommended_action: str
    recommended_window: str
    risk_if_deferred: str
    human_review_required: bool
    evidence: dict[str, object]
    confidence: str
    limitations: list[str]
    lifecycle_state: str
    as_of_timestamp: datetime
    expires_at: datetime | None
    policy_version: str
    created_at: datetime
