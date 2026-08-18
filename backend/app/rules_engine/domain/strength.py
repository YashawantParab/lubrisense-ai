"""Combining evidence strength across more than one corroborating finding (used by
cross-signal/bearing pattern rules — a pattern's strength is never simply invented, it is
derived from the strength of the single-signal evidence it is built from). Pure functions,
no database.
"""

from __future__ import annotations

from app.domain.enums import EvidenceStrength

_STRENGTH_ORDER = (EvidenceStrength.LOW, EvidenceStrength.MODERATE, EvidenceStrength.STRONG)


def weakest(strengths: list[EvidenceStrength]) -> EvidenceStrength:
    """A pattern is only as strong as its weakest *required* piece of evidence."""
    return min(strengths, key=_STRENGTH_ORDER.index)


def escalate_one(strength: EvidenceStrength) -> EvidenceStrength:
    """One additional, independently-corroborating signal raises confidence by one level,
    capped at STRONG — never invents evidence beyond what already fired."""
    index = min(_STRENGTH_ORDER.index(strength) + 1, len(_STRENGTH_ORDER) - 1)
    return _STRENGTH_ORDER[index]
