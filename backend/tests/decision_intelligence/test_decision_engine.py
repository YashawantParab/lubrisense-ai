"""Database integration: `DecisionEngine.decide_for_machine()` against real Postgres —
real chain (fresh condition + fresh prognostics), and the supersede-not-overwrite lifecycle
(Phase 14 brief §14.12)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.decision_intelligence.repositories.decision_assessment_repository import (
    DecisionAssessmentRepository,
)
from app.decision_intelligence.services.decision_engine import (
    DecisionEngine,
    DecisionEngineMachineNotFoundError,
)
from tests.rules_engine.helpers import build_machine_with_topology


@pytest.mark.asyncio
async def test_decide_unknown_machine_raises(db_session: AsyncSession) -> None:
    engine = DecisionEngine(db_session)
    with pytest.raises(DecisionEngineMachineNotFoundError):
        await engine.decide_for_machine(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_decide_for_fresh_machine_is_monitor_continue_monitoring(
    db_session: AsyncSession,
) -> None:
    """A fresh, uninstrumented machine has zero condition evidence -> INSUFFICIENT_EVIDENCE
    -> a verification/monitoring decision, never a fabricated maintenance action."""
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    engine = DecisionEngine(db_session)
    bundle = await engine.decide_for_machine(tenant.id, machine.id)

    assert bundle.condition.condition_type.value == "INSUFFICIENT_EVIDENCE"
    assert bundle.decision.recommended_action.value == "REQUEST_ADDITIONAL_MEASUREMENT"
    assert bundle.decision.human_review_required is False
    assert bundle.decision.lifecycle_state.value == "ACTIVE"
    assert bundle.decision.condition_assessment_id == bundle.condition.id


@pytest.mark.asyncio
async def test_second_decision_supersedes_first_without_deleting_it(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    engine = DecisionEngine(db_session)

    first_bundle = await engine.decide_for_machine(tenant.id, machine.id)
    second_bundle = await engine.decide_for_machine(tenant.id, machine.id)

    repo = DecisionAssessmentRepository(db_session)
    all_decisions = await repo.list_for_machine(tenant.id, machine.id)
    assert len(all_decisions) == 2

    first_row = next(d for d in all_decisions if d.id == first_bundle.decision.id)
    second_row = next(d for d in all_decisions if d.id == second_bundle.decision.id)
    assert first_row.lifecycle_state.value == "SUPERSEDED"
    assert second_row.lifecycle_state.value == "ACTIVE"


@pytest.mark.asyncio
async def test_get_latest_returns_the_most_recent_active_decision(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    engine = DecisionEngine(db_session)

    await engine.decide_for_machine(tenant.id, machine.id)
    second_bundle = await engine.decide_for_machine(tenant.id, machine.id)

    repo = DecisionAssessmentRepository(db_session)
    latest = await repo.get_latest(tenant.id, machine.id)
    assert latest is not None
    assert latest.id == second_bundle.decision.id
