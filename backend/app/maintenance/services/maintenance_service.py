"""`MaintenanceService` — Phase 17 human-controlled maintenance workflow orchestration.

No physical maintenance action is ever executed automatically (Phase 17 brief §17.3) —
this service only ever records what a human recommended/planned/performed/found. Case
completion requires an explicit technician feedback classification plus a fresh, real
post-action `ConditionEngine` re-check — never a bare state click (§17.8, ADR-133).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.condition_intelligence.repositories.condition_assessment_repository import (
    ConditionAssessmentRepository,
)
from app.condition_intelligence.services.condition_engine import ConditionEngine
from app.decision_intelligence.repositories.decision_assessment_repository import (
    DecisionAssessmentRepository,
)
from app.domain.enums import (
    FeedbackClassification,
    IncidentEventType,
    MaintenanceActionType,
    MaintenanceState,
    TechnicianFindingResult,
)
from app.domain.models import FeedbackRecord, MaintenanceAction, MaintenanceCase, TechnicianFinding
from app.incidents.services.incident_service import IncidentService
from app.maintenance.checklist_templates import resolve_checklist
from app.maintenance.observability import METRICS
from app.maintenance.repositories.feedback_repository import FeedbackRepository
from app.maintenance.repositories.maintenance_action_repository import MaintenanceActionRepository
from app.maintenance.repositories.maintenance_case_repository import MaintenanceCaseRepository
from app.maintenance.repositories.technician_finding_repository import (
    TechnicianFindingRepository,
)

_PHYSICAL_ACTIONS = frozenset(
    {
        MaintenanceActionType.CLEANED,
        MaintenanceActionType.REFILLED,
        MaintenanceActionType.COMPONENT_REPLACED,
        MaintenanceActionType.ADJUSTMENT_RECOMMENDED,
    }
)


class MaintenanceCaseNotFoundError(LookupError):
    pass


class InvalidMaintenanceTransitionError(ValueError):
    def __init__(self, current: MaintenanceState, action: str) -> None:
        super().__init__(f"Cannot {action} a maintenance case in state {current.value}.")


class MaintenanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cases = MaintenanceCaseRepository(session)
        self._findings = TechnicianFindingRepository(session)
        self._actions = MaintenanceActionRepository(session)
        self._feedback = FeedbackRepository(session)
        self._incidents = IncidentService(session)
        self._conditions = ConditionAssessmentRepository(session)
        self._decisions = DecisionAssessmentRepository(session)
        self._condition_engine = ConditionEngine(session)

    async def create_case_for_incident(
        self, tenant_id: uuid.UUID, incident_id: uuid.UUID
    ) -> MaintenanceCase:
        """Idempotent — returns the existing active case for this incident if one
        already exists (Phase 17 brief §17.4: "one incident may create or link to one
        MaintenanceCase"), backed by `uq_maintenance_case_active_incident`."""
        existing = await self._cases.get_active_for_incident(tenant_id, incident_id)
        if existing is not None:
            return existing

        incident = await self._incidents.get(tenant_id, incident_id)
        decision_id = uuid.UUID(incident.decision_assessment_ids[-1])
        condition_id = uuid.UUID(incident.condition_assessment_ids[-1])
        decision = await self._decisions.get_by_id(tenant_id, decision_id)
        condition = await self._conditions.get_by_id(tenant_id, condition_id)
        if decision is None or condition is None:
            raise MaintenanceCaseNotFoundError(
                f"Incident {incident_id} references evidence that no longer exists."
            )

        template_id, checklist_items = resolve_checklist(decision.recommended_action.value)
        case = MaintenanceCase(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            incident_id=incident_id,
            machine_id=incident.machine_id,
            component_id=incident.component_id,
            condition_assessment_id=condition.id,
            decision_assessment_id=decision.id,
            recommended_action=decision.recommended_action,
            recommended_window=decision.recommended_window,
            priority=decision.priority,
            human_review_required=decision.human_review_required,
            state=(
                MaintenanceState.REVIEW_REQUIRED
                if decision.human_review_required
                else MaintenanceState.NOT_STARTED
            ),
            checklist=[{"text": item, "completed": False} for item in checklist_items],
            checklist_template_id=template_id,
            policy_version=decision.policy_version,
        )
        case = await self._cases.insert(case)
        METRICS.increment("maintenance_cases_created")
        return case

    async def get(self, tenant_id: uuid.UUID, case_id: uuid.UUID) -> MaintenanceCase:
        case = await self._cases.get(tenant_id, case_id)
        if case is None:
            raise MaintenanceCaseNotFoundError(str(case_id))
        return case

    async def list_cases(
        self, tenant_id: uuid.UUID, *, state: MaintenanceState | None = None, limit: int = 200
    ) -> list[MaintenanceCase]:
        return await self._cases.list_for_tenant(tenant_id, state=state, limit=limit)

    async def plan(
        self, tenant_id: uuid.UUID, case_id: uuid.UUID, *, planned_for: datetime | None
    ) -> MaintenanceCase:
        case = await self.get(tenant_id, case_id)
        if case.state not in (MaintenanceState.REVIEW_REQUIRED, MaintenanceState.NOT_STARTED):
            raise InvalidMaintenanceTransitionError(case.state, "plan")
        case.state = MaintenanceState.PLANNED
        case.planned_for = planned_for
        case = await self._cases.save(case)

        incident = await self._incidents.get(tenant_id, case.incident_id)
        if incident.state.value == "INVESTIGATING":
            await self._incidents.mark_action_planned(tenant_id, case.incident_id)
        return case

    async def start(self, tenant_id: uuid.UUID, case_id: uuid.UUID) -> MaintenanceCase:
        case = await self.get(tenant_id, case_id)
        if case.state != MaintenanceState.PLANNED:
            raise InvalidMaintenanceTransitionError(case.state, "start")
        case.state = MaintenanceState.IN_PROGRESS
        case.started_at = datetime.now(UTC)
        return await self._cases.save(case)

    async def record_finding(
        self,
        tenant_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        result: TechnicianFindingResult,
        component: str | None,
        observed_issue: str | None,
        notes: str,
        technician_identifier: str,
    ) -> TechnicianFinding:
        case = await self.get(tenant_id, case_id)
        if case.state in (MaintenanceState.COMPLETED, MaintenanceState.CANCELLED):
            raise InvalidMaintenanceTransitionError(case.state, "record a finding for")

        finding = await self._findings.insert(
            TechnicianFinding(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                maintenance_case_id=case_id,
                result=result,
                component=component,
                observed_issue=observed_issue,
                notes=notes,
                technician_identifier=technician_identifier,
                attachments_metadata=[],
                recorded_at=datetime.now(UTC),
            )
        )
        await self._incidents.record_related_event(
            tenant_id,
            case.incident_id,
            IncidentEventType.TECHNICIAN_FINDING_RECORDED,
            f"Technician finding recorded: {result.value}.",
        )
        METRICS.increment("technician_findings_recorded")
        return finding

    async def record_action(
        self,
        tenant_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        action_type: MaintenanceActionType,
        notes: str,
        recorded_by: str,
    ) -> MaintenanceAction:
        case = await self.get(tenant_id, case_id)
        if case.state not in (MaintenanceState.IN_PROGRESS, MaintenanceState.AWAITING_VERIFICATION):
            raise InvalidMaintenanceTransitionError(case.state, "record an action for")

        action = await self._actions.insert(
            MaintenanceAction(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                maintenance_case_id=case_id,
                action_type=action_type,
                notes=notes,
                recorded_by=recorded_by,
                recorded_at=datetime.now(UTC),
            )
        )
        if action_type in _PHYSICAL_ACTIONS and case.state == MaintenanceState.IN_PROGRESS:
            case.state = MaintenanceState.AWAITING_VERIFICATION
            await self._cases.save(case)
        METRICS.increment("maintenance_actions_recorded")
        return action

    async def complete(
        self,
        tenant_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        classification: FeedbackClassification,
        notes: str,
        recorded_by: str,
        confirmed_component: str | None = None,
        confirmed_finding: str | None = None,
    ) -> MaintenanceCase:
        """Requires an explicit technician feedback classification AND performs a real,
        fresh post-action condition re-check (never completes solely because an endpoint
        was called — Phase 17 brief §17.8)."""
        case = await self.get(tenant_id, case_id)
        if case.state not in (MaintenanceState.IN_PROGRESS, MaintenanceState.AWAITING_VERIFICATION):
            raise InvalidMaintenanceTransitionError(case.state, "complete")

        post_condition = await self._condition_engine.assess(tenant_id, case.machine_id)

        await self._feedback.insert(
            FeedbackRecord(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                maintenance_case_id=case_id,
                incident_id=case.incident_id,
                condition_assessment_id=case.condition_assessment_id,
                decision_assessment_id=case.decision_assessment_id,
                classification=classification,
                confirmed_component=confirmed_component,
                confirmed_finding=confirmed_finding,
                post_action_condition_type=post_condition.condition_type.value,
                notes=notes,
                recorded_by=recorded_by,
                recorded_at=datetime.now(UTC),
            )
        )

        case.feedback_classification = classification
        case.state = MaintenanceState.COMPLETED
        case.completed_at = datetime.now(UTC)
        case = await self._cases.save(case)

        await self._incidents.resolve(
            tenant_id,
            case.incident_id,
            reason=(
                f"Maintenance case completed with feedback {classification.value}; "
                f"post-action condition is {post_condition.condition_type.value}."
            ),
        )
        METRICS.increment("maintenance_cases_completed")
        METRICS.increment(f"feedback_{classification.value.lower()}")
        return case

    async def cancel(
        self, tenant_id: uuid.UUID, case_id: uuid.UUID, *, reason: str
    ) -> MaintenanceCase:
        case = await self.get(tenant_id, case_id)
        if case.state in (MaintenanceState.COMPLETED, MaintenanceState.CANCELLED):
            raise InvalidMaintenanceTransitionError(case.state, "cancel")
        case.state = MaintenanceState.CANCELLED
        case = await self._cases.save(case)
        await self._incidents.record_related_event(
            tenant_id,
            case.incident_id,
            IncidentEventType.EVIDENCE_ADDED,
            f"Maintenance case cancelled: {reason}.",
        )
        return case

    async def list_findings(
        self, tenant_id: uuid.UUID, case_id: uuid.UUID
    ) -> list[TechnicianFinding]:
        await self.get(tenant_id, case_id)
        return await self._findings.list_for_case(tenant_id, case_id)

    async def list_actions(
        self, tenant_id: uuid.UUID, case_id: uuid.UUID
    ) -> list[MaintenanceAction]:
        await self.get(tenant_id, case_id)
        return await self._actions.list_for_case(tenant_id, case_id)

    async def get_feedback(self, tenant_id: uuid.UUID, case_id: uuid.UUID) -> FeedbackRecord | None:
        await self.get(tenant_id, case_id)
        return await self._feedback.get_for_case(tenant_id, case_id)
