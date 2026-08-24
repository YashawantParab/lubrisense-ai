"""Pure energy-residual math and status derivation — no I/O, no database, mirroring
`app.baselines.domain.deviation`/`app.condition_intelligence.services.synthesis`'s own
"pure logic separate from orchestration" split so this is exhaustively unit-testable
without a session or fixtures.

Lubrication Efficiency Intelligence, Pass 1 (docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md
§4-§8, ADR-176). Builds no new statistical method — `deviation_classification` here is
always `app.baselines.domain.deviation.compute_deviation`'s own real output, reused
directly (see `app.energy.services.energy_assessment_service`).
"""

from __future__ import annotations

from app.baselines.domain.deviation import DeviationResult
from app.domain.enums import DeviationClassification, EnergyAssessmentStatus, QualityState


def compute_residual(
    actual_power_kw: float, expected_power_kw: float
) -> tuple[float, float | None]:
    """`residual_pct` is `None` when `expected_power_kw <= 0` — a non-positive expected
    value makes a percentage deviation meaningless (could be an arbitrarily large or
    undefined ratio), so this deliberately returns "no percentage" rather than a
    misleading number (brief's own "do not calculate misleading percentages when
    denominator is invalid")."""
    residual_kw = actual_power_kw - expected_power_kw
    residual_pct = (residual_kw / expected_power_kw) * 100.0 if expected_power_kw > 0 else None
    return residual_kw, residual_pct


def determine_status(
    *,
    has_power_reading: bool,
    quality_state: QualityState,
    deviation: DeviationResult | None,
    residual_kw: float | None,
) -> EnergyAssessmentStatus:
    """`deviation` is `None` only when no baseline could even be resolved (no
    `ResolvedBaseline.profile` at all) — distinct from `DeviationClassification
    .NOT_ENOUGH_DATA`, which `compute_deviation` itself never returns (that classification
    is `deviation_service.evaluate`'s own `not_enough_data()` sentinel for the same "no
    resolved profile" case) — both map to `INSUFFICIENT_BASELINE` here, so callers may
    pass either shape."""
    if not has_power_reading:
        return EnergyAssessmentStatus.INSUFFICIENT_DATA
    if quality_state == QualityState.UNUSABLE:
        return EnergyAssessmentStatus.DATA_QUALITY_LIMITED
    if deviation is None or deviation.classification == DeviationClassification.NOT_ENOUGH_DATA:
        return EnergyAssessmentStatus.INSUFFICIENT_BASELINE
    if deviation.classification == DeviationClassification.WITHIN_EXPECTED_RANGE:
        return EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE
    # MILD_DEVIATION or STRONG_DEVIATION — direction (not just magnitude) decides which
    # one; compute_deviation only ever tells us the latter.
    if residual_kw is None:
        return EnergyAssessmentStatus.INSUFFICIENT_BASELINE
    return (
        EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND
        if residual_kw > 0
        else EnergyAssessmentStatus.BELOW_EXPECTED_RANGE
    )
