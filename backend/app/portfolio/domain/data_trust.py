"""Pure data-trust rollup — no I/O, no database (Portfolio Intelligence Pass 1,
ADR-177, docs/PORTFOLIO_INTELLIGENCE.md §"data-trust rollup").

`overall_quality_state` intentionally mirrors
`app.condition_intelligence.services.condition_engine._overall_quality_state`'s own
worst-of policy (three-tier TRUSTED/CAUTION/NO_TRUSTED_DATA rollup over one machine's own
sensors) rather than importing that private helper across module boundaries — the logic
is three lines, and duplicating it here with an explicit citation is clearer than
reaching into another module's underscore-prefixed internals.

`derive_data_trust_category` never averages sensor quality into one score — see
`DataTrustCategory`'s own docstring: a site with 95% trusted sensors but one blocked
critical asset must still surface that limitation, which only a categorical per-machine
judgment (aggregated as counts) can do.
"""

from __future__ import annotations

from app.domain.enums import DataTrustCategory, QualityState

_OverallQuality = str  # "TRUSTED" | "CAUTION" | "NO_TRUSTED_DATA"


def overall_quality_state(sensor_quality_states: list[QualityState]) -> _OverallQuality:
    """Worst-of rollup over one machine's own sensors — mirrors `ConditionEngine
    ._overall_quality_state` exactly (see module docstring)."""
    if not sensor_quality_states:
        return "NO_TRUSTED_DATA"
    if any(q == QualityState.USABLE_WITH_CAUTION for q in sensor_quality_states):
        return "CAUTION"
    if all(q == QualityState.UNUSABLE for q in sensor_quality_states):
        return "NO_TRUSTED_DATA"
    return "TRUSTED"


def derive_data_trust_category(
    *, overall_quality: _OverallQuality, has_open_workflow: bool
) -> DataTrustCategory:
    """`has_open_workflow` (an unresolved incident and/or non-terminal maintenance case)
    escalates a quality limitation from merely reduced-confidence to actively blocking a
    real, needed action — `ACTION_BLOCKED` outranks `ASSESSMENT_BLOCKED`/
    `CONFIDENCE_REDUCED` when both co-occur, since it is the more urgent framing."""
    if overall_quality == "NO_TRUSTED_DATA":
        return (
            DataTrustCategory.ACTION_BLOCKED
            if has_open_workflow
            else DataTrustCategory.ASSESSMENT_BLOCKED
        )
    if overall_quality == "CAUTION":
        return (
            DataTrustCategory.ACTION_BLOCKED
            if has_open_workflow
            else DataTrustCategory.CONFIDENCE_REDUCED
        )
    return DataTrustCategory.DECISION_EVIDENCE_TRUSTED
