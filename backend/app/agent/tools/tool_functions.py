"""The explicit, allowlisted tool functions (Phase 19 brief §19.2). Every one wraps a
real, already-existing platform service — never arbitrary SQL, and never a mutating
lifecycle method (acknowledge/resolve/close/plan/start/complete/record_finding/
record_action/CMMS submission are structurally absent from this module and therefore
cannot be registered as tools — see `app.agent.tools.registry.ALLOWED_TOOLS`).

`generate_checklist_draft`/`draft_work_order` are the only two tools that produce a
`DraftArtifact` (Phase 19 brief §19.15/§19.16) — `draft_work_order` does call the real
`CMMSService.create_draft`, which is itself already local-draft-only and idempotent
(Phase 20), so this is a real, safe, persisted local draft, never an external submission.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from app.agent.domain.models import DraftArtifact, ToolResult
from app.agent.tools.context import ToolContext
from app.cmms.services.cmms_service import CMMSService, CMMSUnavailableError
from app.condition_intelligence.services.condition_query_service import (
    ConditionQueryMachineNotFoundError,
    ConditionQueryService,
)
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.decision_intelligence.services.decision_query_service import (
    DecisionQueryMachineNotFoundError,
    DecisionQueryService,
)
from app.domain.enums import QualityState
from app.features.repositories.source_repository import FeatureSourceRepository
from app.incidents.services.incident_service import IncidentNotFoundError, IncidentService
from app.maintenance.services.maintenance_service import (
    MaintenanceCaseNotFoundError,
    MaintenanceService,
)
from app.prognostics.services.prognostic_query_service import (
    PrognosticQueryMachineNotFoundError,
    PrognosticQueryService,
)
from app.repositories.machine import MachineRepository


def _require(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not value:
        raise ValueError(f"Tool argument '{key}' is required.")
    return str(value)


async def get_asset_context(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    machine_id = uuid.UUID(_require(arguments, "machine_id"))
    machine = await MachineRepository(ctx.session).get(ctx.tenant_id, machine_id)
    if machine is None:
        return ToolResult("get_asset_context", "ERROR", "Machine not found.")
    data = {
        "machine_id": str(machine.id),
        "name": machine.name,
        "asset_code": machine.asset_code,
        "machine_type": machine.machine_type.value,
        "criticality": machine.criticality.value,
    }
    return ToolResult("get_asset_context", "OK", f"{machine.name} ({machine.asset_code}).", data)


async def get_current_condition(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    machine_id = uuid.UUID(_require(arguments, "machine_id"))
    try:
        condition = await ConditionQueryService(ctx.session).latest(ctx.tenant_id, machine_id)
    except ConditionQueryMachineNotFoundError:
        return ToolResult("get_current_condition", "ERROR", "Machine not found.")
    if condition is None:
        return ToolResult("get_current_condition", "OK", "No condition assessment yet.")
    data = {
        "id": str(condition.id),
        "condition_type": condition.condition_type.value,
        "severity": condition.severity.value,
        "confidence": condition.confidence.value,
        "lifecycle_state": condition.lifecycle_state.value,
        "what_is_happening": str(condition.evidence_summary.get("what_is_happening", "")),
        "why": list(condition.evidence_summary.get("why", [])),
    }
    return ToolResult(
        "get_current_condition",
        "OK",
        f"{condition.condition_type.value} ({condition.severity.value}).",
        data,
    )


async def get_current_decision(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    machine_id = uuid.UUID(_require(arguments, "machine_id"))
    try:
        decision = await DecisionQueryService(ctx.session).latest(ctx.tenant_id, machine_id)
    except DecisionQueryMachineNotFoundError:
        return ToolResult("get_current_decision", "ERROR", "Machine not found.")
    if decision is None:
        return ToolResult("get_current_decision", "OK", "No decision assessment yet.")
    data = {
        "id": str(decision.id),
        "condition_assessment_id": str(decision.condition_assessment_id),
        "priority": decision.priority.value,
        "recommended_action": decision.recommended_action.value,
        "recommended_window": decision.recommended_window.value,
        "risk_if_deferred": decision.risk_if_deferred,
        "human_review_required": decision.human_review_required,
        "confidence": decision.confidence.value,
    }
    return ToolResult(
        "get_current_decision",
        "OK",
        f"{decision.recommended_action.value} ({decision.priority.value}).",
        data,
    )


async def get_current_prognostic(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    machine_id = uuid.UUID(_require(arguments, "machine_id"))
    try:
        forecasts = await PrognosticQueryService(ctx.session).latest(ctx.tenant_id, machine_id)
    except PrognosticQueryMachineNotFoundError:
        return ToolResult("get_current_prognostic", "ERROR", "Machine not found.")
    data = {
        "forecasts": [
            {
                "state_type": f.state_type.value,
                "horizon": f.horizon.value,
                "status": f.status.value,
                "predicted_state_at_horizon": f.predicted_state_at_horizon,
            }
            for f in forecasts
        ]
    }
    return ToolResult(
        "get_current_prognostic", "OK", f"{len(forecasts)} forecast(s) available.", data
    )


async def get_incident(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    incident_id = uuid.UUID(_require(arguments, "incident_id"))
    try:
        incident = await IncidentService(ctx.session).get(ctx.tenant_id, incident_id)
    except IncidentNotFoundError:
        return ToolResult("get_incident", "ERROR", "Incident not found.")
    data = {
        "id": str(incident.id),
        "title": incident.title,
        "summary": incident.summary,
        "incident_type": incident.incident_type.value,
        "severity": incident.severity.value,
        "priority": incident.priority.value,
        "state": incident.state.value,
    }
    return ToolResult("get_incident", "OK", incident.title, data)


async def get_incident_timeline(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    incident_id = uuid.UUID(_require(arguments, "incident_id"))
    try:
        events = await IncidentService(ctx.session).timeline(ctx.tenant_id, incident_id)
    except IncidentNotFoundError:
        return ToolResult("get_incident_timeline", "ERROR", "Incident not found.")
    data = {"events": [{"event_type": e.event_type.value, "summary": e.summary} for e in events]}
    return ToolResult("get_incident_timeline", "OK", f"{len(events)} timeline event(s).", data)


async def get_maintenance_case(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    """Includes the technician's outcome (feedback classification + most recent finding)
    when they exist — without these, the assistant has no grounded way to answer
    "was the diagnosis confirmed?" or "what did the technician find?", and would either
    refuse or (worse) guess."""
    case_id = uuid.UUID(_require(arguments, "case_id"))
    service = MaintenanceService(ctx.session)
    try:
        case = await service.get(ctx.tenant_id, case_id)
    except MaintenanceCaseNotFoundError:
        return ToolResult("get_maintenance_case", "ERROR", "Maintenance case not found.")
    findings = await service.list_findings(ctx.tenant_id, case_id)
    feedback = await service.get_feedback(ctx.tenant_id, case_id)
    latest_finding = findings[-1] if findings else None
    data = {
        "id": str(case.id),
        "state": case.state.value,
        "recommended_action": case.recommended_action.value,
        "checklist": case.checklist,
        "checklist_template_id": case.checklist_template_id,
        "latest_finding_observed_issue": latest_finding.observed_issue if latest_finding else None,
        "latest_finding_result": latest_finding.result.value if latest_finding else None,
        "feedback_classification": feedback.classification.value if feedback else None,
        "post_action_condition_type": feedback.post_action_condition_type if feedback else None,
    }
    return ToolResult("get_maintenance_case", "OK", f"Case state: {case.state.value}.", data)


async def get_telemetry_summary(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    machine_id = uuid.UUID(_require(arguments, "machine_id"))
    registered = await FeatureSourceRepository(ctx.session).registered_sensors(
        ctx.tenant_id, machine_id
    )
    quality_rows = await SensorQualityStateRepository(ctx.session).list_for_machine(
        ctx.tenant_id, machine_id
    )
    unusable = sum(1 for row in quality_rows if row.quality_state == QualityState.UNUSABLE)
    data = {
        "registered_sensor_count": len(registered),
        "reporting_sensor_count": len(quality_rows),
        "unusable_sensor_count": unusable,
    }
    return ToolResult(
        "get_telemetry_summary",
        "OK",
        f"{len(registered)} registered sensor(s), {len(quality_rows)} reporting.",
        data,
    )


async def search_approved_documentation(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    from app.domain.enums import DocumentType
    from app.knowledge.services.retriever import Retriever

    query = _require(arguments, "query")
    procedure_types = [t.value for t in DocumentType if t != DocumentType.SERVICE_CASE]
    results = await Retriever(ctx.session).search(
        ctx.tenant_id, query, document_types=procedure_types
    )
    data = {
        "results": [
            {
                "document_title": r.citation.document_title,
                "document_version": r.citation.document_version,
                "heading": r.citation.heading,
                "excerpt": r.excerpt,
                "citation": dataclasses.asdict(r.citation),
            }
            for r in results
        ]
    }
    return ToolResult(
        "search_approved_documentation", "OK", f"{len(results)} approved result(s).", data
    )


async def search_similar_service_cases(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    from app.domain.enums import DocumentType
    from app.knowledge.services.retriever import Retriever

    query = _require(arguments, "query")
    results = await Retriever(ctx.session).search(
        ctx.tenant_id, query, document_types=[DocumentType.SERVICE_CASE.value]
    )
    data = {
        "results": [
            {
                "document_title": r.citation.document_title,
                "excerpt": r.excerpt,
                "citation": dataclasses.asdict(r.citation),
            }
            for r in results
        ]
    }
    return ToolResult(
        "search_similar_service_cases", "OK", f"{len(results)} similar case(s).", data
    )


async def generate_checklist_draft(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    """Never silently replaces the deterministic Phase 17 checklist (Phase 19 brief
    §19.16) — returns it as-is, wrapped as a `DraftArtifact`, for the agent to
    summarize/present; the mandatory items themselves are untouched."""
    case_id = uuid.UUID(_require(arguments, "case_id"))
    try:
        case = await MaintenanceService(ctx.session).get(ctx.tenant_id, case_id)
    except MaintenanceCaseNotFoundError:
        return ToolResult("generate_checklist_draft", "ERROR", "Maintenance case not found.")
    artifact = DraftArtifact(
        kind="CHECKLIST_DRAFT",
        content={
            "maintenance_case_id": str(case.id),
            "checklist_template_id": case.checklist_template_id,
            "items": case.checklist,
        },
    )
    return ToolResult(
        "generate_checklist_draft",
        "OK",
        f"Checklist draft prepared from template {case.checklist_template_id}.",
        {"draft_artifact": artifact},
    )


async def draft_work_order(ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    """Calls the real, already-idempotent, draft-only `CMMSService.create_draft`
    (Phase 20) — output remains DRAFT, never externally submitted (Phase 19 brief
    §19.15)."""
    case_id = uuid.UUID(_require(arguments, "case_id"))
    try:
        record = await CMMSService(ctx.session).create_draft(ctx.tenant_id, case_id)
    except MaintenanceCaseNotFoundError:
        return ToolResult("draft_work_order", "ERROR", "Maintenance case not found.")
    except CMMSUnavailableError as exc:
        return ToolResult("draft_work_order", "ERROR", f"CMMS draft unavailable: {exc}")
    artifact = DraftArtifact(
        kind="WORK_ORDER_DRAFT",
        content={
            "external_reference": record.external_reference,
            "title": record.title,
            "status": record.status,
            "checklist": record.checklist,
        },
    )
    return ToolResult(
        "draft_work_order",
        "OK",
        f"Work order draft {record.external_reference} prepared ({record.status}).",
        {"draft_artifact": artifact},
    )
