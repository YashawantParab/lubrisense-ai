"""Pure, explainable incident correlation logic (Phase 16 brief §16.4). No opaque ML
clustering — correlation is a deterministic string built from tenant/machine/component/
condition-family, exactly the same mechanism `RuleFinding` already uses for its own
active-scope idempotency (ADR-078), one layer up.
"""

from __future__ import annotations

import uuid

from app.incidents.config.policy import IncidentCorrelationPolicy

# Condition types that never independently create or update an incident (Phase 16 brief
# §16.1/§16.11, "HEALTHY CASE"/"AMBIGUOUS CASE"/"SENSOR / DATA QUALITY CASE"). Reused
# verbatim from Phase 14's `decision_synthesis._NON_FAULT_TYPES` (ADR-119) — the same
# fault-vs-non-fault boundary applies one layer up: if it could not manufacture a
# maintenance decision, it must not manufacture an incident either.
_NO_INCIDENT_CONDITION_TYPES = frozenset(
    {
        "NORMAL_OPERATION",
        "INSUFFICIENT_EVIDENCE",
        "SENSOR_OR_DATA_QUALITY_LIMITATION",
        "AMBIGUOUS_CONDITION",
    }
)


def family_for_condition_type(condition_type: str, policy: IncidentCorrelationPolicy) -> str | None:
    """`None` means: this condition type never creates/updates an equipment incident —
    either it is a non-fault type (see `_NO_INCIDENT_CONDITION_TYPES`) or genuinely
    unmapped in policy."""
    if condition_type in _NO_INCIDENT_CONDITION_TYPES:
        return None
    return policy.condition_family_map.get(condition_type)


def build_correlation_key(
    machine_id: uuid.UUID, component_id: uuid.UUID | None, family: str
) -> str:
    """Deterministic — same machine + component + family always yields the same key, so
    the database's own partial-unique-index (`uq_incident_active_correlation_key`) can
    enforce "at most one open incident per evolving problem" without any application-level
    locking."""
    component_part = str(component_id) if component_id is not None else "NONE"
    return f"{machine_id}:{component_part}:{family}"
