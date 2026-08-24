"""Observable-only ENERGY_RESIDUAL evidence (Lubrication Efficiency Intelligence, Pass 1
— docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §8/§13, ADR-176).

Produces an `EvidenceItem`-shaped description of one `EnergyAssessment`, in the exact
shape `ConditionEngine._evidence_from_rule_finding`/`_evidence_from_ml_result`/
`_evidence_from_state_estimate` already use — so a *future* pass can wire this into
`ConditionEngine.assess()` by adding one more `_evidence_from_energy_assessment`-shaped
method, without inventing a new evidence contract.

Deliberately NOT called anywhere in `app.condition_intelligence` yet: this pass produces
real, persisted energy evidence, but the platform's actual condition/decision output is
completely unaffected by it (CLAUDE.md's "implement only the current phase" discipline).
Nothing in `ConditionEngine.assess()` imports this module.
"""

from __future__ import annotations

from app.condition_intelligence.domain.models import EvidenceItem
from app.domain.enums import EnergyAssessmentStatus
from app.domain.models import EnergyAssessment

#: Only a genuine deviation is evidence — mirrors the design doc's own "energy deviation
#: is a measured fact; it is an EVIDENCE ITEM only once it is materially interesting"
#: framing. `WITHIN_EXPECTED_RANGE` and every insufficient/limited status produce no
#: evidence item at all (`None`), the same "absent, not weak" distinction
#: `_evidence_from_ml_result` draws for `INSUFFICIENT_FEATURES`.
_EVIDENCE_STATUSES = frozenset(
    {EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND, EnergyAssessmentStatus.BELOW_EXPECTED_RANGE}
)


def energy_residual_evidence(assessment: EnergyAssessment) -> EvidenceItem | None:
    """`condition_hint` is always `None`: an energy residual is fault-agnostic by
    construction (design doc §8 — "energy evidence alone can never independently
    establish a condition"), the same real limitation `_evidence_from_ml_result` already
    documents for Isolation-Forest anomaly evidence. `strength` is correspondingly capped
    at `"WEAK"` always — mirroring that same anomaly-evidence precedent exactly
    (`condition_hint=None` items structurally never enter `synthesize()`'s vote tally
    regardless of strength, so `WEAK` is the honest ceiling here too, not an arbitrary
    choice)."""
    if assessment.status not in _EVIDENCE_STATUSES:
        return None
    if assessment.residual_pct is not None:
        magnitude = f"{assessment.residual_pct:+.1f}%"
    elif assessment.residual_kw is not None:
        magnitude = f"{assessment.residual_kw:+.2f} kW"
    else:
        return None
    description = (
        f"Machine power is {magnitude} relative to its contextual expected range "
        f"(status={assessment.status.value})."
    )
    return EvidenceItem(
        source_type="ENERGY_RESIDUAL",
        source_id=str(assessment.id),
        strength="WEAK",
        condition_hint=None,
        description=description,
    )
