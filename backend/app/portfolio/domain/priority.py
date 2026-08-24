"""Pure portfolio-attention-priority derivation — no I/O, no database (Portfolio
Intelligence Pass 1, ADR-177, docs/PORTFOLIO_INTELLIGENCE.md §"risk/priority model").

Deterministic, explainable, versioned (`POLICY_VERSION`) — never a fabricated numeric
score. Reliability/safety evidence is always primary: energy/carbon evidence can only
ever raise a machine from `MONITOR` to `ATTENTION` on its own, never higher — it is never
allowed to outrank a genuine condition/incident/maintenance-urgency signal, and is always
recorded as a supplementary reason, never the deciding one, when anything else already
justifies `ATTENTION` or above.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import (
    ActionReadinessState,
    ConditionConfidence,
    ConditionSeverity,
    ConditionType,
    Criticality,
    DecisionPriority,
    EnergyAssessmentStatus,
    PortfolioPriority,
)

POLICY_VERSION = "1"

#: Ordinal rank each `PortfolioPriority` level below `DATA_LIMITED` corresponds to —
#: `DATA_LIMITED` is resolved separately (§ below), never reached via this scale.
_RANK_TO_PRIORITY = {
    0: PortfolioPriority.MONITOR,
    1: PortfolioPriority.ATTENTION,
    2: PortfolioPriority.HIGH_ATTENTION,
    3: PortfolioPriority.CRITICAL_ATTENTION,
}


@dataclass(frozen=True)
class PriorityInput:
    action_readiness: ActionReadinessState
    condition_type: ConditionType | None
    condition_severity: ConditionSeverity | None
    condition_confidence: ConditionConfidence | None
    criticality: Criticality
    has_open_incident: bool
    incident_severity: ConditionSeverity | None
    has_open_maintenance: bool
    maintenance_priority: DecisionPriority | None
    energy_status: EnergyAssessmentStatus | None
    attribution_level_is_supporting: bool


@dataclass(frozen=True)
class PriorityResult:
    priority: PortfolioPriority
    reasons: tuple[str, ...] = field(default_factory=tuple)
    policy_version: str = POLICY_VERSION


def derive_priority(inp: PriorityInput) -> PriorityResult:
    if inp.action_readiness in (
        ActionReadinessState.NOT_YET_ASSESSED,
        ActionReadinessState.ASSESSMENT_BLOCKED,
    ):
        reason = (
            "condition has never been assessed"
            if inp.action_readiness == ActionReadinessState.NOT_YET_ASSESSED
            else "insufficient evidence to reach a reliable condition assessment"
        )
        return PriorityResult(PortfolioPriority.DATA_LIMITED, (reason,))

    rank = 0
    reasons: list[str] = []

    if inp.condition_severity == ConditionSeverity.CRITICAL:
        rank = max(rank, 3)
        reasons.append(f"condition severity CRITICAL ({_type_label(inp.condition_type)})")
    elif inp.condition_severity == ConditionSeverity.HIGH:
        rank = max(rank, 2)
        reasons.append(f"condition severity HIGH ({_type_label(inp.condition_type)})")
    elif inp.condition_severity == ConditionSeverity.WARNING:
        rank = max(rank, 1)
        reasons.append(f"condition severity WARNING ({_type_label(inp.condition_type)})")

    if inp.has_open_incident:
        if inp.incident_severity in (ConditionSeverity.CRITICAL, ConditionSeverity.HIGH):
            rank = max(rank, 3)
            reasons.append("unresolved incident at high/critical severity")
        else:
            rank = max(rank, 2)
            reasons.append("unresolved incident")

    if inp.has_open_maintenance:
        if inp.maintenance_priority == DecisionPriority.URGENT:
            rank = max(rank, 3)
            reasons.append("urgent maintenance action pending")
        elif inp.maintenance_priority == DecisionPriority.HIGH:
            rank = max(rank, 2)
            reasons.append("high-priority maintenance action pending")
        else:
            rank = max(rank, 1)
            reasons.append("maintenance action pending")

    if inp.criticality == Criticality.CRITICAL and rank >= 2:
        rank = 3
        reasons.append("critical asset criticality")
    elif inp.criticality == Criticality.HIGH and rank == 1:
        rank = 2
        reasons.append("high asset criticality")

    if inp.condition_confidence == ConditionConfidence.LOW and rank == 3:
        rank = 2
        reasons.append("condition confidence LOW — capped below CRITICAL_ATTENTION")

    if inp.energy_status == EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND:
        reasons.append("elevated contextual energy demand")
        if inp.attribution_level_is_supporting:
            reasons.append("lubrication-attribution evidence supports the energy deviation")
        # Energy evidence alone never outranks reliability/safety evidence — it can only
        # raise the floor from MONITOR to ATTENTION, never higher, on its own.
        rank = max(rank, 1)

    if not reasons:
        reasons.append("no active reliability or energy concerns")

    return PriorityResult(_RANK_TO_PRIORITY[rank], tuple(reasons))


def _type_label(condition_type: ConditionType | None) -> str:
    return condition_type.value if condition_type is not None else "condition"
