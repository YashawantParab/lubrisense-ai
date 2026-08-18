"""What a rule hands back — not yet persisted. `RuleFindingRepository` turns this into a
`RuleFinding` row; kept as a plain dataclass so rules stay pure functions (mirroring
`app.data_quality.domain.results.RuleIssue`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import EvidenceStrength, RuleCategory, RuleFindingType


@dataclass(frozen=True)
class RuleFindingCandidate:
    finding_type: RuleFindingType
    rule_id: str
    rule_version: str
    category: RuleCategory
    component_type: str
    component_id: uuid.UUID | None
    evidence_strength: EvidenceStrength
    message: str
    """A short, calibrated-language summary (`docs/RULES_ENGINE.md` "Causal language") —
    the structured `evidence` dict is the actual output, this is a human-readable label for
    it, never the sole output (Phase 9 brief §6)."""
    evidence: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    """What this specific finding does NOT prove (Phase 9 brief §26) — always non-empty for
    a cross-signal/pattern finding."""
    source_event_ids: list[str] = field(default_factory=list)
    baseline_version_ids: list[str] = field(default_factory=list)
    quality_context: dict[str, Any] = field(default_factory=dict)
