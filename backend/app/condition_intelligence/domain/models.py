"""Label-free, config-agnostic condition-intelligence contracts. `ConditionEvidence` is
gathered from real Phase 7/9/11/12 output; `ConditionAssessmentResult` is the synthesis
outcome, persisted as `app.domain.models.ConditionAssessment` by the repository. Nothing
here imports `simulator` — only real, already-persisted evidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One vote toward a condition hypothesis (Phase 13 brief §13.7). `strength`
    determines whether this item can independently establish a condition
    (`STRONG`/`SUPPORTING`) or only corroborate one another item has already established
    (`WEAK`), or is recorded for transparency but excluded from the vote tally entirely
    (`EXPERIMENTAL` — an EXPERIMENT-status ML model's output, §13.3)."""

    source_type: str  # "RULE_FINDING" | "ML_RESULT" | "STATE_ESTIMATE"
    source_id: str
    strength: str  # "STRONG" | "SUPPORTING" | "WEAK" | "EXPERIMENTAL"
    condition_hint: str | None  # a ConditionType value, or None (abstains from voting)
    description: str
    #: The `RuleFindingSeverity` this item's own source already computed, when it has one
    #: (only `RULE_FINDING` items do) — carried as a real field, not parsed out of
    #: `description`, so `_severity_for` never depends on string formatting.
    severity: str | None = None


@dataclass(frozen=True, slots=True)
class ConditionEvidence:
    """Everything `ConditionEngine.assess()` gathered for one machine at one moment —
    the input to the pure `synthesize()` function."""

    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    as_of_timestamp: datetime
    criticality: str
    items: tuple[EvidenceItem, ...]
    quality_context: dict[str, object]
    instrumentation_coverage: dict[str, object]
    baseline_versions: dict[str, object]
    rule_finding_ids: tuple[str, ...]
    ml_result_ids: tuple[str, ...]
    state_estimate_ids: tuple[str, ...]
    limitations: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ConditionAssessmentResult:
    """Pure synthesis output — the `ConditionEngine`'s answer to "what is happening, why,
    and how sure are we" (Phase 13 brief §13.12), before lifecycle history is applied."""

    condition_type: str
    severity: str
    confidence: str
    what_is_happening: str
    why: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    data_trustworthiness: str
    unknowns: tuple[str, ...]
    recommended_next_evidence: str | None
