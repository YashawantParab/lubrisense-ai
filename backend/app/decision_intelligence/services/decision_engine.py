"""`DecisionEngine` — the top of the intelligence chain (Phase 14 brief). Triggers a fresh
Phase 13 `ConditionAssessment` and a fresh Phase 15 forecast set, then synthesizes one
`DecisionAssessment` from them via the pure `decide()` function
(`services/decision_synthesis.py`). This is the only layer whose output is meant to
trigger a human maintenance action — see `human_review_required` on every physical action.

Never consumes simulator ground truth. Criticality (`Machine.criticality`) may shift
priority up or down; it can never manufacture a fault-pattern decision from
NORMAL_OPERATION/AMBIGUOUS_CONDITION/INSUFFICIENT_EVIDENCE/SENSOR_OR_DATA_QUALITY_
LIMITATION evidence (Phase 14 brief §14.4, enforced structurally in
`decision_synthesis._NON_FAULT_TYPES`).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.condition_intelligence.services.condition_engine import ConditionEngine
from app.decision_intelligence.config.policy import (
    DecisionIntelligencePolicy,
    load_decision_intelligence_policy,
)
from app.decision_intelligence.domain.models import ConditionSnapshot, ProgSnapshot
from app.decision_intelligence.observability import METRICS
from app.decision_intelligence.repositories.decision_assessment_repository import (
    DecisionAssessmentRepository,
)
from app.decision_intelligence.services.decision_synthesis import decide
from app.domain.models import ConditionAssessment, DecisionAssessment, PrognosticAssessment
from app.prognostics.services.prognostic_engine import PrognosticEngine
from app.repositories.machine import MachineRepository


class DecisionEngineMachineNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class DecisionBundle:
    condition: ConditionAssessment
    prognostics: list[PrognosticAssessment]
    decision: DecisionAssessment


def _condition_snapshot(row: ConditionAssessment) -> ConditionSnapshot:
    return ConditionSnapshot(
        id=str(row.id),
        condition_type=row.condition_type.value,
        lifecycle_state=row.lifecycle_state.value,
        severity=row.severity.value,
        confidence=row.confidence.value,
        what_is_happening=str(row.evidence_summary.get("what_is_happening", "")),
    )


def _prognostic_snapshot(row: PrognosticAssessment) -> ProgSnapshot:
    return ProgSnapshot(
        id=str(row.id),
        status=row.status.value,
        threshold_crossing_seconds=(
            (row.estimated_threshold_crossing_time - row.as_of_timestamp).total_seconds()
            if row.estimated_threshold_crossing_time is not None
            else None
        ),
    )


class DecisionEngine:
    def __init__(
        self, session: AsyncSession, policy: DecisionIntelligencePolicy | None = None
    ) -> None:
        self._session = session
        self._policy = policy or load_decision_intelligence_policy()
        self._machines = MachineRepository(session)
        self._condition_engine = ConditionEngine(session)
        self._prognostic_engine = PrognosticEngine(session)
        self._decisions = DecisionAssessmentRepository(session)

    async def decide_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> DecisionBundle:
        started = time.perf_counter()
        machine = await self._machines.get(tenant_id, machine_id)
        if machine is None:
            raise DecisionEngineMachineNotFoundError(str(machine_id))

        try:
            condition = await self._condition_engine.assess(tenant_id, machine_id)
            prognostics = await self._prognostic_engine.forecast_machine(tenant_id, machine_id)

            result = decide(
                _condition_snapshot(condition),
                [_prognostic_snapshot(p) for p in prognostics],
                machine.criticality.value,
                self._policy,
            )

            now = datetime.now(UTC)
            assessment = DecisionAssessment(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                machine_id=machine_id,
                component_id=None,
                condition_assessment_id=condition.id,
                prognostic_assessment_id=prognostics[0].id if prognostics else None,
                priority=result.priority,
                recommended_action=result.recommended_action,
                recommended_window=result.recommended_window,
                risk_if_deferred=result.risk_if_deferred,
                human_review_required=result.human_review_required,
                evidence=result.evidence,
                confidence=result.confidence,
                limitations=list(result.limitations),
                lifecycle_state="ACTIVE",
                as_of_timestamp=now,
                expires_at=now + timedelta(seconds=result.expires_in_seconds),
                policy_version=self._policy.policy_version,
            )
            persisted = await self._decisions.insert_and_supersede_prior(assessment)
        except Exception:
            METRICS.increment("intelligence_processing_errors")
            raise

        METRICS.increment("decision_assessments_created")
        if result.priority == "URGENT":
            METRICS.increment("urgent_decisions")
        METRICS.set_gauge("intelligence_processing_duration", time.perf_counter() - started)
        return DecisionBundle(condition=condition, prognostics=prognostics, decision=persisted)
