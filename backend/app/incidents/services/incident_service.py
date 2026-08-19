"""`IncidentService` — Phase 16 alert correlation + incident lifecycle orchestration.

`evaluate_machine()` triggers a fresh, full `DecisionEngine.decide_for_machine()` call
(the same ADR-125 "always fresh chain" pattern Phase 14 established) and either creates a
new incident, correlates evidence into an existing open one, or resolves open incidents on
recovery — never spamming N incidents for N evaluation cycles of the same evolving
problem (Phase 16 brief §16.1/§16.10).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditActor, AuditService
from app.decision_intelligence.services.decision_engine import DecisionBundle, DecisionEngine
from app.domain.enums import IncidentEventType, IncidentState
from app.domain.models import Incident, IncidentEvent, Machine
from app.incidents.config.policy import IncidentCorrelationPolicy, load_incident_correlation_policy
from app.incidents.observability import METRICS
from app.incidents.repositories.incident_event_repository import IncidentEventRepository
from app.incidents.repositories.incident_repository import IncidentRepository
from app.incidents.services.correlation import build_correlation_key, family_for_condition_type
from app.incidents.services.lifecycle import validate_transition
from app.repositories.machine import MachineRepository


class IncidentServiceMachineNotFoundError(LookupError):
    pass


class IncidentNotFoundError(LookupError):
    pass


def _title_for(machine_name: str, condition_type: str) -> str:
    return f"{condition_type.replace('_', ' ').title()} — {machine_name}"


class IncidentService:
    def __init__(
        self, session: AsyncSession, policy: IncidentCorrelationPolicy | None = None
    ) -> None:
        self._session = session
        self._policy = policy or load_incident_correlation_policy()
        self._machines = MachineRepository(session)
        self._incidents = IncidentRepository(session)
        self._events = IncidentEventRepository(session)
        self._decision_engine = DecisionEngine(session)

    async def evaluate_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> Incident | None:
        """Returns the created/updated open incident, or `None` when current evidence
        does not warrant one (healthy, ambiguous, insufficient evidence, or data-quality
        limitation — Phase 16 brief §16.1/§16.11)."""
        machine = await self._machines.get(tenant_id, machine_id)
        if machine is None:
            raise IncidentServiceMachineNotFoundError(str(machine_id))

        bundle = await self._decision_engine.decide_for_machine(tenant_id, machine_id)
        condition_type = bundle.condition.condition_type.value

        if condition_type == "NORMAL_OPERATION":
            await self._resolve_open_incidents(
                tenant_id, machine_id, reason="Condition returned to NORMAL_OPERATION."
            )
            return None

        family = family_for_condition_type(condition_type, self._policy)
        if family is None:
            # INSUFFICIENT_EVIDENCE / SENSOR_OR_DATA_QUALITY_LIMITATION /
            # AMBIGUOUS_CONDITION: evidence is not yet actionable, but is also not
            # confirmed resolved — never spam a new incident, and never touch an existing
            # open one just because this one evaluation cycle was inconclusive.
            METRICS.increment("incident_evaluation_no_incident")
            return None

        correlation_key = build_correlation_key(machine_id, bundle.condition.component_id, family)
        existing = await self._incidents.get_open_by_correlation_key(
            tenant_id, machine_id, correlation_key
        )
        if existing is not None:
            METRICS.increment("incident_evidence_correlated")
            return await self._append_evidence(existing, bundle)

        METRICS.increment("incident_created")
        return await self._create_incident(tenant_id, machine, bundle, correlation_key)

    async def _create_incident(
        self,
        tenant_id: uuid.UUID,
        machine: Machine,
        bundle: DecisionBundle,
        correlation_key: str,
    ) -> Incident:
        condition = bundle.condition
        now = datetime.now(UTC)
        incident = Incident(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            machine_id=machine.id,
            component_id=condition.component_id,
            correlation_key=correlation_key,
            incident_type=condition.condition_type,
            title=_title_for(machine.name, condition.condition_type.value),
            summary=str(condition.evidence_summary.get("what_is_happening", "")),
            severity=condition.severity,
            priority=bundle.decision.priority,
            state=IncidentState.OPEN,
            first_detected_at=now,
            last_updated_at=now,
            condition_assessment_ids=[str(condition.id)],
            decision_assessment_ids=[str(bundle.decision.id)],
            prognostic_assessment_ids=[str(p.id) for p in bundle.prognostics],
            rule_finding_ids=list(condition.rule_finding_ids),
            ml_result_ids=list(condition.ml_result_ids),
            state_estimate_ids=list(condition.state_estimate_ids),
            evidence_refs={"why": list(condition.evidence_summary.get("why", []))},
            policy_version=self._policy.policy_version,
            engine_version=self._policy.engine_version,
        )
        incident = await self._incidents.insert(incident)
        await self._append_event(
            incident,
            IncidentEventType.INCIDENT_CREATED,
            f"Incident created from {condition.condition_type.value} "
            f"({condition.severity.value}/{bundle.decision.priority.value}).",
        )
        await AuditService(self._session).record(
            tenant_id,
            actor=AuditActor.system("incident-service"),
            action="INCIDENT_CREATED",
            entity_type="incident",
            entity_id=incident.id,
            source="incident_service.evaluate_machine",
            after_summary=(
                f"{incident.incident_type.value} ({incident.severity.value}/"
                f"{incident.priority.value}) on machine {machine.id}."
            ),
        )
        return incident

    async def _append_evidence(self, incident: Incident, bundle: DecisionBundle) -> Incident:
        condition = bundle.condition
        now = datetime.now(UTC)

        if str(condition.id) not in incident.condition_assessment_ids:
            incident.condition_assessment_ids = [
                *incident.condition_assessment_ids,
                str(condition.id),
            ]
        if str(bundle.decision.id) not in incident.decision_assessment_ids:
            incident.decision_assessment_ids = [
                *incident.decision_assessment_ids,
                str(bundle.decision.id),
            ]
        for prog in bundle.prognostics:
            if str(prog.id) not in incident.prognostic_assessment_ids:
                incident.prognostic_assessment_ids = [
                    *incident.prognostic_assessment_ids,
                    str(prog.id),
                ]
        for fid in condition.rule_finding_ids:
            if fid not in incident.rule_finding_ids:
                incident.rule_finding_ids = [*incident.rule_finding_ids, fid]
        for mid in condition.ml_result_ids:
            if mid not in incident.ml_result_ids:
                incident.ml_result_ids = [*incident.ml_result_ids, mid]
        for sid in condition.state_estimate_ids:
            if sid not in incident.state_estimate_ids:
                incident.state_estimate_ids = [*incident.state_estimate_ids, sid]

        if incident.severity != condition.severity:
            old = incident.severity.value
            incident.severity = condition.severity
            await self._append_event(
                incident,
                IncidentEventType.SEVERITY_CHANGED,
                f"Severity changed from {old} to {condition.severity.value}.",
            )
        if incident.priority != bundle.decision.priority:
            old = incident.priority.value
            incident.priority = bundle.decision.priority
            await self._append_event(
                incident,
                IncidentEventType.PRIORITY_CHANGED,
                f"Priority changed from {old} to {bundle.decision.priority.value}.",
            )

        incident.incident_type = condition.condition_type
        incident.summary = str(
            condition.evidence_summary.get("what_is_happening", incident.summary)
        )
        incident.last_updated_at = now
        await self._append_event(
            incident,
            IncidentEventType.EVIDENCE_ADDED,
            f"New evidence linked from a fresh {condition.condition_type.value} assessment.",
        )
        return await self._incidents.save(incident)

    async def _resolve_open_incidents(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, *, reason: str
    ) -> None:
        for incident in await self._incidents.list_open_for_machine(tenant_id, machine_id):
            await self._transition(incident, IncidentState.RESOLVED, reason)
            await self._incidents.save(incident)

    async def get(self, tenant_id: uuid.UUID, incident_id: uuid.UUID) -> Incident:
        incident = await self._incidents.get(tenant_id, incident_id)
        if incident is None:
            raise IncidentNotFoundError(str(incident_id))
        return incident

    async def list_incidents(
        self,
        tenant_id: uuid.UUID,
        *,
        machine_id: uuid.UUID | None = None,
        state: IncidentState | None = None,
        limit: int = 200,
    ) -> list[Incident]:
        return await self._incidents.list_for_tenant(
            tenant_id, machine_id=machine_id, state=state, limit=limit
        )

    async def timeline(self, tenant_id: uuid.UUID, incident_id: uuid.UUID) -> list[IncidentEvent]:
        await self.get(tenant_id, incident_id)
        return await self._events.list_for_incident(tenant_id, incident_id)

    async def acknowledge(self, tenant_id: uuid.UUID, incident_id: uuid.UUID) -> Incident:
        incident = await self.get(tenant_id, incident_id)
        await self._transition(
            incident, IncidentState.ACKNOWLEDGED, "Incident acknowledged by a technician."
        )
        incident.acknowledged_at = datetime.now(UTC)
        return await self._incidents.save(incident)

    async def start_investigation(self, tenant_id: uuid.UUID, incident_id: uuid.UUID) -> Incident:
        incident = await self.get(tenant_id, incident_id)
        await self._transition(incident, IncidentState.INVESTIGATING, "Investigation started.")
        return await self._incidents.save(incident)

    async def mark_action_planned(self, tenant_id: uuid.UUID, incident_id: uuid.UUID) -> Incident:
        incident = await self.get(tenant_id, incident_id)
        await self._transition(
            incident, IncidentState.ACTION_PLANNED, "Maintenance action planned."
        )
        return await self._incidents.save(incident)

    async def resolve(
        self, tenant_id: uuid.UUID, incident_id: uuid.UUID, *, reason: str
    ) -> Incident:
        incident = await self.get(tenant_id, incident_id)
        await self._transition(incident, IncidentState.RESOLVED, reason)
        return await self._incidents.save(incident)

    async def close(self, tenant_id: uuid.UUID, incident_id: uuid.UUID) -> Incident:
        """Closing is always an explicit human action (Phase 16 brief §16.11) — never
        triggered automatically by recovery/resolution."""
        incident = await self.get(tenant_id, incident_id)
        await self._transition(incident, IncidentState.CLOSED, "Incident closed.")
        return await self._incidents.save(incident)

    async def record_related_event(
        self,
        tenant_id: uuid.UUID,
        incident_id: uuid.UUID,
        event_type: IncidentEventType,
        summary: str,
    ) -> Incident:
        """Appends a timeline event WITHOUT a state transition — used by downstream
        packages (e.g. `app.maintenance`) to record something relevant on an incident's
        timeline (a technician finding, a cancelled case) that does not itself change the
        incident's own lifecycle state."""
        incident = await self.get(tenant_id, incident_id)
        incident.last_updated_at = datetime.now(UTC)
        await self._append_event(incident, event_type, summary)
        return await self._incidents.save(incident)

    async def reopen(
        self, tenant_id: uuid.UUID, incident_id: uuid.UUID, *, reason: str
    ) -> Incident:
        incident = await self.get(tenant_id, incident_id)
        await self._transition(incident, IncidentState.REOPENED, reason)
        return await self._incidents.save(incident)

    async def _transition(self, incident: Incident, target: IncidentState, reason: str) -> None:
        current = incident.state
        validate_transition(current, target)
        incident.state = target
        now = datetime.now(UTC)
        incident.last_updated_at = now
        if target == IncidentState.ACKNOWLEDGED:
            event_type = IncidentEventType.ACKNOWLEDGED
        elif target == IncidentState.INVESTIGATING:
            event_type = IncidentEventType.INVESTIGATION_STARTED
        elif target == IncidentState.ACTION_PLANNED:
            event_type = IncidentEventType.ACTION_PLANNED
        elif target == IncidentState.RESOLVED:
            event_type = IncidentEventType.RESOLVED
            incident.resolved_at = now
        elif target == IncidentState.CLOSED:
            event_type = IncidentEventType.CLOSED
            incident.closed_at = now
        elif target == IncidentState.REOPENED:
            event_type = IncidentEventType.REOPENED
            incident.resolved_at = None
            incident.closed_at = None
        else:
            event_type = IncidentEventType.EVIDENCE_ADDED
        await self._append_event(incident, event_type, reason)

    async def _append_event(
        self, incident: Incident, event_type: IncidentEventType, summary: str
    ) -> None:
        await self._events.insert(
            IncidentEvent(
                id=uuid.uuid4(),
                tenant_id=incident.tenant_id,
                incident_id=incident.id,
                event_type=event_type,
                summary=summary,
                details={},
                recorded_at=datetime.now(UTC),
            )
        )
