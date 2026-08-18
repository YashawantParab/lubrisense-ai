"""What a quality rule hands back — not yet persisted. `QualityIssueRepository` turns this
into a `QualityIssue` row; kept as a plain dataclass so rules stay pure functions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType


@dataclass(frozen=True)
class RuleIssue:
    dimension: QualityDimension
    issue_type: QualityIssueType
    severity: IssueSeverity
    message: str
    rule_id: str
    rule_version: str
    evidence: dict[str, Any] = field(default_factory=dict)
    affected_event_ids: list[str] = field(default_factory=list)
    # Exactly one scope populated: event_id for an event-scoped issue, window_start/
    # window_end for a window-scoped one (app.domain.enums.AssessmentScope).
    event_id: uuid.UUID | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
