"""Metric-kind-agnostic "how far is this candidate from a reference" helper — the single
divergence computation `app.baselines.services.baseline_engine`'s contamination-control
state machine uses, whether the reference is a `STANDARD` numeric distribution, a
`RESERVOIR_TREND`, or a `CYCLE_METRIC` (Phase 8 brief §23/§41). Operates on the persisted
JSONB `dict` shape directly (the same shape every strategy's `.to_dict()` produces), not on
the dataclasses themselves, since a candidate/anchor pair may already be sitting in a DB row.
"""

from __future__ import annotations

from typing import Any

from app.domain.enums import BaselineMetricKind

_PRIMARY_FIELD = {
    BaselineMetricKind.STANDARD: ("median", "mad"),
    BaselineMetricKind.RESERVOIR_TREND: (
        "median_depletion_rate_percent_per_hour",
        "depletion_rate_mad",
    ),
    BaselineMetricKind.CYCLE_METRIC: ("median_duration_seconds", "duration_mad"),
}


def primary_metric(metric_kind: BaselineMetricKind, stats: dict[str, Any]) -> tuple[float, float]:
    value_field, spread_field = _PRIMARY_FIELD[metric_kind]
    return float(stats[value_field]), float(stats[spread_field])


def mad_distance(
    candidate: dict[str, Any], reference: dict[str, Any], metric_kind: BaselineMetricKind
) -> float:
    """Distance of `candidate` from `reference`, scaled by `reference`'s own spread — using
    the reference's spread (not the candidate's) keeps the yardstick fixed while the
    candidate moves, which is what makes the anchor-vs-candidate comparison in
    `baseline_engine.py` meaningful across cycles."""
    candidate_value, _ = primary_metric(metric_kind, candidate)
    reference_value, reference_spread = primary_metric(metric_kind, reference)
    if reference_spread > 0:
        return abs(candidate_value - reference_value) / reference_spread
    return 0.0 if candidate_value == reference_value else float("inf")
