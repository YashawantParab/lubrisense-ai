"""`LocalEdgeAlert` — output of `edge.rules.LocalRuleEngine` (Phase 5 brief §16-§17).

Deliberately structurally separate from any future `ConditionAssessment`
(docs/EVENT_CATALOG.md §4.1 `LocalAlarmRaised`): this is a deterministic, edge-local,
two-state (`OPEN`/`CLEARED`) alert, not a diagnosis. Rule ids use generic labels
(`LOCAL_WARNING`, `LOCAL_SENSOR_FAULT`, `LOCAL_RANGE_VIOLATION`,
`LOCAL_LUBRICATION_CYCLE_FAILURE`) — never a domain-specific diagnosis like "restriction
detected" (Phase 9's job, not Phase 5's).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from edge.domain.enums import AlertSeverity, AlertStatus


class LocalEdgeAlert(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alert_id: str
    timestamp: datetime
    tenant_id: uuid.UUID
    gateway_id: str
    machine_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    sensor_id: uuid.UUID | None = None
    rule_id: str
    severity: AlertSeverity
    message: str
    evidence: dict[str, Any] = {}
    source_event_ids: list[str] = []
    status: AlertStatus = AlertStatus.OPEN
