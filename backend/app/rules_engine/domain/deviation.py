"""Classifies a robust standardized distance into `DeviationClassification` — the same
three-way bucket `app.baselines.domain.deviation.compute_deviation` produces for
`STANDARD`-kind baselines, applied here to `app.baselines.domain.anchor.mad_distance`'s
output for `RESERVOIR_TREND`/`CYCLE_METRIC`-kind baselines (which `compute_deviation`
itself does not cover — it is scoped to a value vs. a numeric distribution, not a trend/
cycle-shaped baseline). Pure function, no database.
"""

from __future__ import annotations

from app.domain.enums import DeviationClassification, EvidenceStrength

_MODERATE_OR_STRONG = (
    DeviationClassification.MILD_DEVIATION,
    DeviationClassification.STRONG_DEVIATION,
)
_STRENGTH_ORDER = (EvidenceStrength.LOW, EvidenceStrength.MODERATE, EvidenceStrength.STRONG)


def classify_distance(
    distance: float, *, mild_multiplier: float, strong_multiplier: float
) -> DeviationClassification:
    if distance <= mild_multiplier:
        return DeviationClassification.WITHIN_EXPECTED_RANGE
    if distance <= strong_multiplier:
        return DeviationClassification.MILD_DEVIATION
    return DeviationClassification.STRONG_DEVIATION


def is_material(classification: DeviationClassification) -> bool:
    return classification in _MODERATE_OR_STRONG


def evidence_strength_for(
    classification: DeviationClassification,
    *,
    caution: bool,
    caution_cap: EvidenceStrength,
) -> EvidenceStrength:
    """`MILD_DEVIATION` -> `MODERATE`, `STRONG_DEVIATION` -> `STRONG` (Phase 9 brief §8),
    then capped at `caution_cap` if the evidence came from an `ELIGIBLE_WITH_CAUTION`
    sensor (brief §4's "evidence strength reduced")."""
    base = (
        EvidenceStrength.STRONG
        if classification == DeviationClassification.STRONG_DEVIATION
        else EvidenceStrength.MODERATE
    )
    if not caution:
        return base
    return min(base, caution_cap, key=_STRENGTH_ORDER.index)
