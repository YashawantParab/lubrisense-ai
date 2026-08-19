"""Phase 19 guarded-agent API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.schemas.knowledge import CitationResponse


class ChatRequest(BaseModel):
    message: str
    session_id: uuid.UUID | None = None
    machine_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    maintenance_case_id: uuid.UUID | None = None


class ToolCallResponse(BaseModel):
    tool_name: str
    status: str
    summary: str


class DraftArtifactResponse(BaseModel):
    kind: str
    content: dict[str, object]


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    answer: str
    evidence: list[str]
    citations: list[CitationResponse]
    tool_calls: list[ToolCallResponse]
    draft_artifacts: list[DraftArtifactResponse]
    limitations: list[str]
    human_review_required: bool


class AgentSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID | None
    incident_id: uuid.UUID | None
    maintenance_case_id: uuid.UUID | None
    created_at: datetime


class AgentMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    response_payload: dict[str, object]
    created_at: datetime


class AgentToolCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    tool_name: str
    status: str
    result_summary: str
    correlation_id: str
    created_at: datetime
