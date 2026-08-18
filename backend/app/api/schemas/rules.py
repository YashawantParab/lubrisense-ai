"""Response schemas for `app/api/v1/rules.py` (Phase 9 brief §32)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.enums import (
    EvidenceStrength,
    RuleCategory,
    RuleFindingSeverity,
    RuleFindingState,
    RuleFindingType,
)


class RuleFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    component_type: str
    finding_type: RuleFindingType
    rule_id: str
    rule_version: str
    config_version: str
    category: RuleCategory
    severity: RuleFindingSeverity
    state: RuleFindingState
    evidence_strength: EvidenceStrength
    criticality_at_detection: str | None
    message: str
    evidence: dict[str, Any]
    limitations: list[str]
    quality_context: dict[str, Any]
    baseline_version_ids: list[str]
    source_event_ids: list[str]
    window_start: datetime | None
    window_end: datetime | None
    candidate_stable_cycles: int
    first_detected_at: datetime
    last_detected_at: datetime
    activated_at: datetime | None
    resolved_at: datetime | None


class MachineFindingsResponse(BaseModel):
    machine_id: uuid.UUID
    findings: list[RuleFindingResponse]


class TenantFindingSummaryResponse(BaseModel):
    findings_by_state: dict[str, int]
    findings_by_severity: dict[str, int]
    total_active_findings: int
