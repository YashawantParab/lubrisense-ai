"""Phase 13 condition-intelligence API contracts. Output here is a SYNTHESIS of evidence,
never a diagnosis or maintenance decision — see docs/CONDITION_INTELLIGENCE.md "Purpose"."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConditionAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    condition_type: str
    lifecycle_state: str
    severity: str
    confidence: str
    as_of_timestamp: datetime
    first_detected_at: datetime
    evidence_summary: dict[str, object]
    rule_finding_ids: list[str]
    ml_result_ids: list[str]
    state_estimate_ids: list[str]
    quality_context: dict[str, object]
    baseline_versions: dict[str, object]
    instrumentation_coverage: dict[str, object]
    limitations: list[str]
    recommended_next_evidence: str | None
    policy_version: str
    engine_version: str
    created_at: datetime
