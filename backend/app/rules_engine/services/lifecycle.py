"""The finding-lifecycle debounce/hysteresis state machine (Phase 9 brief §7/§20/§29) — a
pure function so it is fully unit-testable without a database, mirroring
`app.baselines.services.promotion.decide`'s placement and testing convention.
`app.rules_engine.services.rule_engine.RuleEngine` is the only caller; it translates a
`LifecycleAction` into the actual `RuleFindingRepository` call.

Two independent debounce mechanisms, matching `docs/RULES_ENGINE.md` "Debounce and
hysteresis":

- **Onset** (CANDIDATE -> ACTIVE): a rule must fire on `required_stable_cycles`
  *consecutive* evaluation cycles before a finding is promoted to ACTIVE — a
  consecutive-cycle counter, not an exact N-of-M sliding window (brief §20's "3 of 5" is
  approximated this way, same simplification Phase 8's stability gate documents for its own
  candidate/anchor comparison).
- **Recovery** (ACTIVE -> RECOVERING -> RESOLVED): two consecutive clean (non-firing)
  cycles are required before a finding is considered resolved, avoiding flapping on one
  borderline cycle — identical to Phase 7's `QualityIssue` window-scoped lifecycle. A
  CANDIDATE that stops firing before ever reaching ACTIVE resolves directly (it never
  became a confirmed finding, so there is nothing to "recover" from).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.enums import RuleFindingState

_NON_TERMINAL = (RuleFindingState.CANDIDATE, RuleFindingState.ACTIVE, RuleFindingState.RECOVERING)


class LifecycleAction(StrEnum):
    CREATE_CANDIDATE = "CREATE_CANDIDATE"
    ADVANCE_CANDIDATE = "ADVANCE_CANDIDATE"
    ACTIVATE = "ACTIVATE"
    REFRESH_ACTIVE = "REFRESH_ACTIVE"
    REACTIVATE_FROM_RECOVERING = "REACTIVATE_FROM_RECOVERING"
    MARK_RECOVERING = "MARK_RECOVERING"
    RESOLVE = "RESOLVE"
    NOOP = "NOOP"


@dataclass(frozen=True)
class LifecycleDecision:
    action: LifecycleAction
    candidate_stable_cycles: int = 0


def decide(
    *,
    row_exists: bool,
    row_state: RuleFindingState | None,
    row_candidate_stable_cycles: int,
    fired: bool,
    required_stable_cycles: int,
) -> LifecycleDecision:
    if row_exists and row_state not in _NON_TERMINAL:
        # Defensive only: `RuleFindingRepository.get_current` never returns a terminal
        # (RESOLVED) row, so this lineage is effectively fresh.
        row_exists = False

    if fired:
        if not row_exists:
            return LifecycleDecision(LifecycleAction.CREATE_CANDIDATE, candidate_stable_cycles=1)
        if row_state == RuleFindingState.CANDIDATE:
            advanced = row_candidate_stable_cycles + 1
            if advanced >= required_stable_cycles:
                return LifecycleDecision(LifecycleAction.ACTIVATE)
            return LifecycleDecision(
                LifecycleAction.ADVANCE_CANDIDATE, candidate_stable_cycles=advanced
            )
        if row_state == RuleFindingState.ACTIVE:
            return LifecycleDecision(LifecycleAction.REFRESH_ACTIVE)
        assert row_state == RuleFindingState.RECOVERING  # noqa: S101 - exhaustive by _NON_TERMINAL
        return LifecycleDecision(LifecycleAction.REACTIVATE_FROM_RECOVERING)

    if not row_exists:
        return LifecycleDecision(LifecycleAction.NOOP)
    if row_state == RuleFindingState.CANDIDATE:
        return LifecycleDecision(LifecycleAction.RESOLVE)
    if row_state == RuleFindingState.ACTIVE:
        return LifecycleDecision(LifecycleAction.MARK_RECOVERING)
    assert row_state == RuleFindingState.RECOVERING  # noqa: S101 - exhaustive by _NON_TERMINAL
    return LifecycleDecision(LifecycleAction.RESOLVE)
