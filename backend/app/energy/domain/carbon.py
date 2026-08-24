"""Pure carbon-estimation policy — no I/O, no database (Lubrication Efficiency
Intelligence, Pass 4 — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §10-§11, ADR-176).

**Carbon is strictly downstream of a qualified energy outcome — it can never manufacture
an energy benefit.** `estimated_co2e_kg` is computed from exactly one input pair:
`EnergyOutcomeVerification.estimated_avoided_energy_kwh` (already gated to
`QUALIFIED_RECOVERY` only, Pass 3) and one applicable `SiteEmissionFactor`. If either is
missing or invalid, the result is `None`/an ineligible status — never a substituted
default factor, never a value derived from an unqualified/opportunity-only energy state.

**Temporal factor validity policy (design doc §"factor validity"), the defensible choice
documented here**: this implementation does *not* attempt multi-segment integration
across a factor-version boundary (no architecture in this reference platform tracks
sub-period energy integrals against separate temporal factor slices). Instead, a factor is
only considered applicable when its `[effective_from, effective_to)` window fully covers
the energy outcome's own observed period. A period that only partially overlaps a factor's
validity window is marked `FACTOR_NOT_APPLICABLE` rather than silently using whichever
factor happens to be "current" — this is the safer of the two documented options, at the
cost of sometimes reporting no estimate where a more sophisticated split-factor
integration could have produced a (smaller, more complex) one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import CarbonEstimateStatus, EmissionFactorMethod

POLICY_VERSION = "1"

_VALID_FACTOR_UNIT = "kg_co2e_per_kwh"


@dataclass(frozen=True)
class EmissionFactorSnapshot:
    """Only the fields a `CarbonImpactEstimate` actually needs to compute and to
    display provenance for — never the full `SiteEmissionFactor` row."""

    id: str
    factor_value: float
    factor_unit: str
    method: EmissionFactorMethod
    source_name: str
    source_reference: str | None
    jurisdiction: str | None
    effective_from: datetime
    effective_to: datetime | None
    is_active: bool


@dataclass(frozen=True)
class CarbonEligibilityInput:
    qualified_avoided_energy_kwh: float | None
    observed_period_start: datetime | None
    observed_period_end: datetime | None
    factor: EmissionFactorSnapshot | None
    comparison_confidence_is_high: bool


@dataclass(frozen=True)
class CarbonResult:
    status: CarbonEstimateStatus
    estimated_co2e_kg: float | None
    limitations: tuple[str, ...]


def _factor_covers_period(factor: EmissionFactorSnapshot, start: datetime, end: datetime) -> bool:
    if factor.effective_from > start:
        return False
    return not (factor.effective_to is not None and factor.effective_to < end)


def is_valid_factor(factor: EmissionFactorSnapshot) -> bool:
    """Positive, finite value; correct unit; active. Does not check temporal
    applicability — that is period-specific, checked separately in `evaluate_carbon`."""
    if not factor.is_active:
        return False
    if factor.factor_unit != _VALID_FACTOR_UNIT:
        return False
    if not (factor.factor_value > 0):
        return False
    return math.isfinite(factor.factor_value)


def evaluate_carbon(inp: CarbonEligibilityInput) -> CarbonResult:
    limitations: list[str] = []

    if inp.qualified_avoided_energy_kwh is None:
        return CarbonResult(
            CarbonEstimateStatus.NOT_ELIGIBLE,
            None,
            (
                "No qualified avoided energy is available for this machine — carbon "
                "estimation requires a QUALIFIED_RECOVERY energy outcome.",
            ),
        )
    if inp.observed_period_start is None or inp.observed_period_end is None:
        return CarbonResult(
            CarbonEstimateStatus.NOT_ELIGIBLE,
            None,
            ("The qualifying energy outcome has no resolved observed period.",),
        )
    if inp.factor is None:
        return CarbonResult(
            CarbonEstimateStatus.FACTOR_NOT_CONFIGURED,
            None,
            ("No electricity emission factor is configured for this machine's site.",),
        )
    if not is_valid_factor(inp.factor):
        return CarbonResult(
            CarbonEstimateStatus.FACTOR_NOT_APPLICABLE,
            None,
            (
                "The configured emission factor is inactive, uses an unsupported unit, "
                "or is not a positive finite value.",
            ),
        )
    if not _factor_covers_period(inp.factor, inp.observed_period_start, inp.observed_period_end):
        return CarbonResult(
            CarbonEstimateStatus.FACTOR_NOT_APPLICABLE,
            None,
            (
                "The configured emission factor's effective window does not fully "
                "cover the qualifying energy outcome's observed period.",
            ),
        )

    estimated_co2e_kg = inp.qualified_avoided_energy_kwh * inp.factor.factor_value

    if not inp.comparison_confidence_is_high:
        limitations.append(
            "Underlying energy-outcome comparison confidence is not HIGH — this "
            "estimate carries the same reduced confidence."
        )
        return CarbonResult(
            CarbonEstimateStatus.LIMITED_ESTIMATE, estimated_co2e_kg, tuple(limitations)
        )

    return CarbonResult(CarbonEstimateStatus.ESTIMATE_AVAILABLE, estimated_co2e_kg, ())
