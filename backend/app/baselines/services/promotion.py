"""The contamination-control state machine (Phase 8 brief §39/§40/§41) — a pure function
so it is fully unit-testable without a database. `app.baselines.services.baseline_engine`
is the only caller; it translates a `PromotionDecision` into the actual
`BaselineProfileRepository` calls.

Core idea: a candidate must diverge from, then *remain stably diverged* from, the
currently ACTIVE anchor for `required_stable_cycles` consecutive worker cycles before it
replaces the anchor. Critically, "stability" for a diverged candidate is measured
cycle-over-cycle against the *previous candidate snapshot*, not against the fixed anchor —
but the very first divergence check (whether to start candidate-tracking at all) IS against
the fixed anchor. This combination is what prevents both failure modes:

- A single-cycle blip never promotes (needs `required_stable_cycles` consecutive
  confirmations).
- A slow, continuous drift (gradual restriction, sensor drift) never creeps the ACTIVE
  anchor forward one tiny step at a time ("boiling frog") — REFINE_ACTIVE only fires when a
  cycle's stats are still close to the *anchor itself*, so an anchor never moves except
  through an explicit PROMOTE, and PROMOTE only fires once a new candidate level has
  genuinely settled (stayed put across multiple cycles), not while it is still trending.
  During the entire onset window before that happens, the anchor used by
  `app.baselines.domain.deviation` for any live comparison stays the pre-drift value —
  exactly the "baseline remains anchored to valid pre-drift behavior" requirement.

See docs/BASELINES.md "Contamination control" for the full narrative and
TECHNICAL_DECISIONS.md, baseline-contamination-control ADR.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.baselines.config.policy import StabilityGatePolicy
from app.baselines.domain.anchor import mad_distance
from app.domain.enums import BaselineMetricKind, BaselineState


class UpdateAction(StrEnum):
    FREEZE = "FREEZE"
    CREATE_INSUFFICIENT = "CREATE_INSUFFICIENT"
    START_CANDIDATE = "START_CANDIDATE"
    ADVANCE_CANDIDATE = "ADVANCE_CANDIDATE"
    ACTIVATE = "ACTIVATE"
    PROMOTE = "PROMOTE"
    REFINE_ACTIVE = "REFINE_ACTIVE"


@dataclass(frozen=True)
class PromotionDecision:
    action: UpdateAction
    candidate_stable_cycles: int = 0


_ANCHOR_STATES = (BaselineState.ACTIVE, BaselineState.STALE)


def decide(
    *,
    row_exists: bool,
    row_state: BaselineState | None,
    row_statistics: dict[str, Any] | None,
    row_candidate_statistics: dict[str, Any] | None,
    row_candidate_stable_cycles: int,
    new_stats: dict[str, Any] | None,
    new_sample_count: int,
    min_sample_required: int,
    metric_kind: BaselineMetricKind,
    stability_gate: StabilityGatePolicy,
) -> PromotionDecision:
    if new_stats is None or new_sample_count < min_sample_required:
        if not row_exists:
            return PromotionDecision(UpdateAction.CREATE_INSUFFICIENT)
        return PromotionDecision(UpdateAction.FREEZE)

    if not row_exists:
        return PromotionDecision(UpdateAction.START_CANDIDATE, candidate_stable_cycles=1)

    has_anchor = row_state in _ANCHOR_STATES and row_statistics is not None

    if not has_anchor:
        return _advance_or_restart(
            new_stats,
            reference=row_candidate_statistics,
            stable_cycles=row_candidate_stable_cycles,
            metric_kind=metric_kind,
            stability_gate=stability_gate,
            on_confirmed=UpdateAction.ACTIVATE,
        )

    assert row_statistics is not None  # noqa: S101 - has_anchor guarantees this
    anchor_distance = mad_distance(new_stats, row_statistics, metric_kind)
    if anchor_distance <= stability_gate.candidate_divergence_mad_multiplier:
        return PromotionDecision(UpdateAction.REFINE_ACTIVE)

    return _advance_or_restart(
        new_stats,
        reference=row_candidate_statistics,
        stable_cycles=row_candidate_stable_cycles,
        metric_kind=metric_kind,
        stability_gate=stability_gate,
        on_confirmed=UpdateAction.PROMOTE,
    )


def _advance_or_restart(
    new_stats: dict[str, Any],
    *,
    reference: dict[str, Any] | None,
    stable_cycles: int,
    metric_kind: BaselineMetricKind,
    stability_gate: StabilityGatePolicy,
    on_confirmed: UpdateAction,
) -> PromotionDecision:
    if reference is None:
        return PromotionDecision(UpdateAction.START_CANDIDATE, candidate_stable_cycles=1)
    distance = mad_distance(new_stats, reference, metric_kind)
    if distance > stability_gate.candidate_divergence_mad_multiplier:
        return PromotionDecision(UpdateAction.START_CANDIDATE, candidate_stable_cycles=1)
    advanced = stable_cycles + 1
    if advanced >= stability_gate.required_stable_cycles:
        return PromotionDecision(on_confirmed)
    return PromotionDecision(UpdateAction.ADVANCE_CANDIDATE, candidate_stable_cycles=advanced)
