"""Severity -> (quality_state, eligibility) mapping (Phase 7 brief §26/§27) — one pure
function, applied identically at event- and window-scope, per decision #6 in the plan."""

from __future__ import annotations

from app.data_quality.config.policy import QualityPolicy
from app.domain.enums import Eligibility, IssueSeverity, QualityState

_SEVERITY_ORDER = (
    IssueSeverity.CRITICAL,
    IssueSeverity.ERROR,
    IssueSeverity.WARNING,
    IssueSeverity.INFO,
)


def worst_severity(severities: list[IssueSeverity]) -> IssueSeverity | None:
    for candidate in _SEVERITY_ORDER:
        if candidate in severities:
            return candidate
    return None


def resolve_state(
    severities: list[IssueSeverity], policy: QualityPolicy
) -> tuple[QualityState, Eligibility]:
    worst = worst_severity(severities)
    key = worst.value if worst is not None else "NONE"
    entry = policy.eligibility_mapping[key]
    return entry.quality_state, entry.eligibility
