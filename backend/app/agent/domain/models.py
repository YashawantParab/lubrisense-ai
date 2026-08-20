"""Pure dataclasses for the agent package — no I/O."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.knowledge.domain.models import Citation


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    status: str  # AgentToolCallStatus value: OK / ERROR / DENIED
    summary: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DraftArtifact:
    """A prepared, never-executed workflow artifact (Phase 19 brief §19.3/§19.4) — the
    agent may PREPARE these, never act on them itself."""

    kind: str  # "CHECKLIST_DRAFT" | "WORK_ORDER_DRAFT"
    content: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AnswerSection:
    """One labeled, structured piece of the answer (e.g. "Current condition", "Recent
    significant event") — built deterministically from `evidence` in `AgentService`, never
    by the swappable `LLMProvider` seam, so a real LLM provider can be dropped in later to
    improve `AgentResponse.answer`'s prose without touching what structure the frontend
    renders."""

    key: str
    label: str
    text: str


@dataclass(frozen=True, slots=True)
class AgentResponse:
    session_id: uuid.UUID
    answer: str
    sections: tuple[AnswerSection, ...] = field(default_factory=tuple)
    evidence: tuple[str, ...] = field(default_factory=tuple)
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    tool_calls: tuple[ToolResult, ...] = field(default_factory=tuple)
    draft_artifacts: tuple[DraftArtifact, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    human_review_required: bool = True


@dataclass(frozen=True, slots=True)
class AgentRequest:
    tenant_id: uuid.UUID
    message: str
    session_id: uuid.UUID | None = None
    machine_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    maintenance_case_id: uuid.UUID | None = None
