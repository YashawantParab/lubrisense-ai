"""Tenant-scoped Phase 19 guarded-agent API. The agent explains persisted intelligence
and drafts workflow artifacts — it never acts on the human's behalf. See
docs/GUARDED_AGENT.md "Purpose"."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.models import AgentRequest
from app.agent.observability import METRICS
from app.agent.services.agent_service import AgentService, AgentSessionNotFoundError
from app.api.deps import get_app_settings, get_current_tenant, get_db_session, require_permission
from app.api.schemas.agent import (
    AgentMessageResponse,
    AgentSessionResponse,
    AgentToolCallResponse,
    AnswerSectionResponse,
    ChatRequest,
    ChatResponse,
    DraftArtifactResponse,
    ToolCallResponse,
)
from app.api.schemas.knowledge import CitationResponse
from app.audit.service import AuditActor, AuditService
from app.auth.models import Principal
from app.auth.permissions import Permission
from app.core.config import Settings
from app.domain.models import Tenant

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/metrics")
async def get_agent_metrics() -> Response:
    """Registered before `/sessions/{session_id}` so the literal path `metrics` is never
    mistaken for a session id."""
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.AGENT_USE)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ChatResponse:
    if len(body.message) > settings.agent_message_max_length:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Message exceeds the maximum length of {settings.agent_message_max_length} "
            "characters.",
        )
    service = AgentService(session)
    response = await service.chat(
        AgentRequest(
            tenant_id=tenant.id,
            message=body.message,
            session_id=body.session_id,
            machine_id=body.machine_id,
            incident_id=body.incident_id,
            maintenance_case_id=body.maintenance_case_id,
        )
    )
    METRICS.increment("agent_chat_turns")
    if response.human_review_required:
        METRICS.increment("agent_human_review_required_responses")
    if response.draft_artifacts:
        await AuditService(session).record(
            tenant.id,
            actor=AuditActor.agent("guarded-agent"),
            action="AGENT_DRAFT_GENERATED",
            entity_type="agent_session",
            entity_id=response.session_id,
            source="api.agent.chat",
            after_summary=(
                f"{len(response.draft_artifacts)} draft artifact(s): "
                f"{', '.join(a.kind for a in response.draft_artifacts)}."
            ),
            reason=f"requested_by={principal.user_id}",
        )
    return ChatResponse(
        session_id=response.session_id,
        answer=response.answer,
        sections=[
            AnswerSectionResponse(key=s.key, label=s.label, text=s.text) for s in response.sections
        ],
        evidence=list(response.evidence),
        citations=[CitationResponse(**dataclasses.asdict(c)) for c in response.citations],
        tool_calls=[
            ToolCallResponse(tool_name=t.tool_name, status=t.status, summary=t.summary)
            for t in response.tool_calls
        ],
        draft_artifacts=[
            DraftArtifactResponse(kind=a.kind, content=a.content) for a in response.draft_artifacts
        ],
        limitations=list(response.limitations),
        human_review_required=response.human_review_required,
    )


@router.get("/sessions/{session_id}", response_model=AgentSessionResponse)
async def get_session(
    session_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentSessionResponse:
    service = AgentService(session)
    try:
        agent_session = await service.get_session(tenant.id, session_id)
    except AgentSessionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.") from exc
    return AgentSessionResponse.model_validate(agent_session)


@router.get("/sessions/{session_id}/messages", response_model=list[AgentMessageResponse])
async def list_messages(
    session_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AgentMessageResponse]:
    service = AgentService(session)
    try:
        messages = await service.list_messages(tenant.id, session_id)
    except AgentSessionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.") from exc
    return [AgentMessageResponse.model_validate(m) for m in messages]


@router.get("/sessions/{session_id}/tool-calls", response_model=list[AgentToolCallResponse])
async def list_tool_calls(
    session_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AgentToolCallResponse]:
    service = AgentService(session)
    try:
        tool_calls = await service.list_tool_calls(tenant.id, session_id)
    except AgentSessionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.") from exc
    return [AgentToolCallResponse.model_validate(t) for t in tool_calls]
