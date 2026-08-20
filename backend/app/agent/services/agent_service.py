"""`AgentService` — the guarded workflow assistant (Phase 19 brief §19.1).

Intent classification and tool orchestration happen here, deterministically, in Python —
not inside an LLM call — because `DemoLLMProvider` is a template composer, not a real
function-calling model (see `app.agent.providers.llm_provider` module docstring). This is
what makes the "guarded" boundary structural rather than a prompt instruction: the set of
tools available for a given turn is decided by `app.agent.policy.classify_intent` (reading
only the raw user message) BEFORE any document content is retrieved, so retrieved content
can never expand what this turn is allowed to do (Phase 19 brief §19.18).
"""

from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.models import (
    AgentRequest,
    AgentResponse,
    AnswerSection,
    DraftArtifact,
    ToolResult,
)
from app.agent.policy import PHYSICAL_CONTROL_REFUSAL, classify_intent
from app.agent.providers.llm_provider import DemoLLMProvider, LLMProvider, narrative_sections
from app.agent.repositories.message_repository import AgentMessageRepository
from app.agent.repositories.session_repository import AgentSessionRepository
from app.agent.repositories.tool_call_repository import AgentToolCallRepository
from app.agent.tools.context import ToolContext
from app.agent.tools.registry import call_tool
from app.core.resilience import CircuitBreaker, CircuitOpenError
from app.domain.enums import AgentMessageRole
from app.domain.models import AgentMessage, AgentSession, AgentToolCall
from app.knowledge.domain.models import Citation
from app.knowledge.services.rag_service import INSUFFICIENT_DOCUMENTATION_TEXT

#: Module-level (not per-`AgentService` instance, which is constructed fresh per request
#: like every other service in this codebase) so consecutive-failure state actually
#: accumulates across turns — see `app.core.resilience` module docstring and
#: docs/RESILIENCE.md. Trips after 3 consecutive `compose_answer()` failures; a
#: `DemoLLMProvider` failure is effectively impossible (no I/O), so in practice this only
#: ever engages once a real `ExternalLLMProvider` is configured and starts failing.
_LLM_CIRCUIT_BREAKER = CircuitBreaker(
    name="llm_provider", failure_threshold=3, reset_timeout_seconds=30.0
)


class AgentSessionNotFoundError(LookupError):
    pass


class AgentService:
    def __init__(self, session: AsyncSession, llm_provider: LLMProvider | None = None) -> None:
        self._session = session
        self._provider = llm_provider or DemoLLMProvider()
        self._sessions = AgentSessionRepository(session)
        self._messages = AgentMessageRepository(session)
        self._tool_calls = AgentToolCallRepository(session)

    async def get_session(self, tenant_id: uuid.UUID, session_id: uuid.UUID) -> AgentSession:
        agent_session = await self._sessions.get(tenant_id, session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError(str(session_id))
        return agent_session

    async def list_messages(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[AgentMessage]:
        await self.get_session(tenant_id, session_id)
        return await self._messages.list_for_session(tenant_id, session_id)

    async def list_tool_calls(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[AgentToolCall]:
        await self.get_session(tenant_id, session_id)
        return await self._tool_calls.list_for_session(tenant_id, session_id)

    async def chat(self, request: AgentRequest) -> AgentResponse:
        session = await self._get_or_create_session(request)
        await self._messages.insert(
            AgentMessage(
                id=uuid.uuid4(),
                tenant_id=request.tenant_id,
                session_id=session.id,
                role=AgentMessageRole.USER,
                content=request.message,
                response_payload={},
            )
        )

        intent = classify_intent(request.message)
        correlation_id = uuid.uuid4().hex

        if intent == "PHYSICAL_CONTROL":
            response = AgentResponse(
                session_id=session.id,
                answer=PHYSICAL_CONTROL_REFUSAL,
                limitations=(
                    "Physical control requests are always refused — only informational "
                    "and draft-artifact assistance is available.",
                ),
                human_review_required=True,
            )
            await self._persist_assistant_message(request.tenant_id, session, response)
            return response

        ctx = ToolContext(session=self._session, tenant_id=request.tenant_id)
        tool_results: list[ToolResult] = []
        evidence: dict[str, object] = {}
        draft_artifacts: list[DraftArtifact] = []
        draft_artifact_evidence: list[dict[str, object]] = []
        citations: list[Citation] = []
        limitations: list[str] = []
        human_review_required = True

        async def run(name: str, arguments: dict[str, str]) -> ToolResult:
            result = await call_tool(name, ctx, arguments)
            tool_results.append(result)
            await self._record_tool_call(request.tenant_id, session, result, correlation_id)
            return result

        if request.machine_id is not None:
            machine_arg = {"machine_id": str(request.machine_id)}
            result = await run("get_current_condition", machine_arg)
            if result.status == "OK" and result.data:
                evidence["condition"] = result.data
            result = await run("get_current_decision", machine_arg)
            if result.status == "OK" and result.data:
                evidence["decision"] = result.data
                human_review_required = bool(result.data.get("human_review_required", True))
            result = await run("get_current_prognostic", machine_arg)
            if result.status == "OK" and result.data:
                evidence["prognostic"] = result.data

        if request.incident_id is not None:
            incident_arg = {"incident_id": str(request.incident_id)}
            result = await run("get_incident", incident_arg)
            if result.status == "OK" and result.data:
                evidence["incident"] = result.data
            result = await run("get_incident_timeline", incident_arg)
            if result.status == "OK" and result.data:
                evidence["incident_timeline"] = result.data

        if request.maintenance_case_id is not None:
            case_arg = {"case_id": str(request.maintenance_case_id)}
            result = await run("get_maintenance_case", case_arg)
            if result.status == "OK" and result.data:
                evidence["maintenance_case"] = result.data

        # Enrich the retrieval query with the real, already-fetched condition type (when
        # available) — the user's raw message alone (e.g. "what should I inspect?") is
        # often too generic to distinguish which procedure applies; the condition_type is
        # real, persisted evidence, not an invented keyword, so adding it only sharpens
        # retrieval precision, never changes what grounds the answer.
        condition_evidence = evidence.get("condition")
        search_query = request.message
        if isinstance(condition_evidence, dict):
            condition_type = str(condition_evidence.get("condition_type", ""))
            search_query = f"{request.message} {condition_type.replace('_', ' ').lower()}"

        query_arg = {"query": search_query}
        result = await run("search_approved_documentation", query_arg)
        procedure_results = list(result.data.get("results", [])) if result.status == "OK" else []
        evidence["procedure_results"] = procedure_results
        for item in procedure_results:
            citations.append(Citation(**item["citation"]))

        result = await run("search_similar_service_cases", query_arg)
        service_case_results = list(result.data.get("results", [])) if result.status == "OK" else []
        evidence["service_case_results"] = service_case_results
        for item in service_case_results:
            citations.append(Citation(**item["citation"]))

        rag_status = "SUFFICIENT" if (procedure_results or service_case_results) else "INSUFFICIENT"
        evidence["rag_status"] = rag_status
        if rag_status == "INSUFFICIENT":
            limitations.append(
                "No approved documentation matched this query closely enough to cite."
            )

        if intent == "CHECKLIST_DRAFT":
            if request.maintenance_case_id is not None:
                result = await run(
                    "generate_checklist_draft", {"case_id": str(request.maintenance_case_id)}
                )
                if result.status == "OK":
                    artifact = result.data["draft_artifact"]
                    draft_artifacts.append(artifact)
                    draft_artifact_evidence.append(
                        {"kind": artifact.kind, "content": artifact.content}
                    )
            else:
                limitations.append(
                    "No maintenance case context was provided to generate a checklist draft."
                )

        if intent == "WORK_ORDER_DRAFT":
            if request.maintenance_case_id is not None:
                result = await run(
                    "draft_work_order", {"case_id": str(request.maintenance_case_id)}
                )
                if result.status == "OK":
                    artifact = result.data["draft_artifact"]
                    draft_artifacts.append(artifact)
                    draft_artifact_evidence.append(
                        {"kind": artifact.kind, "content": artifact.content}
                    )
                else:
                    limitations.append(f"Work order draft could not be prepared: {result.summary}")
            else:
                limitations.append(
                    "No maintenance case context was provided to draft a work order."
                )

        if draft_artifact_evidence:
            evidence["draft_artifacts"] = draft_artifact_evidence

        try:
            answer = _LLM_CIRCUIT_BREAKER.call(
                lambda: self._provider.compose_answer(
                    intent=intent, evidence=evidence, message=request.message
                )
            )
        except CircuitOpenError as exc:
            answer = (
                "The assistant's response composition is temporarily unavailable. "
                "The persisted condition, decision, incident, and maintenance-case data "
                "gathered for this question is still available directly via their own "
                "APIs."
            )
            limitations.append(f"LLM provider circuit open, not attempted: {exc}")
        except Exception as exc:  # noqa: BLE001 — provider failure must degrade gracefully,
            # never crash the chat turn or block the rest of the platform (§19.20).
            answer = (
                "The assistant's response composition is temporarily unavailable. "
                "The persisted condition, decision, incident, and maintenance-case data "
                "gathered for this question is still available directly via their own "
                "APIs."
            )
            limitations.append(f"LLM provider unavailable: {exc}")

        has_persisted_context = any(
            key in evidence for key in ("condition", "decision", "incident", "maintenance_case")
        )
        if not has_persisted_context and rag_status == "INSUFFICIENT":
            # Nothing real to ground on at all — the exact required response, never a
            # paraphrase or a fallback to unsupported general knowledge (§19.6/§19.10).
            answer = INSUFFICIENT_DOCUMENTATION_TEXT

        sections = tuple(
            AnswerSection(key=s.key, label=s.label, text=s.text)
            for s in narrative_sections(evidence, request.message)
        )

        response = AgentResponse(
            session_id=session.id,
            answer=answer,
            sections=sections,
            evidence=tuple(r.summary for r in tool_results if r.status == "OK"),
            citations=tuple(citations),
            tool_calls=tuple(tool_results),
            draft_artifacts=tuple(draft_artifacts),
            limitations=tuple(limitations),
            human_review_required=human_review_required,
        )
        await self._persist_assistant_message(request.tenant_id, session, response)
        return response

    async def _get_or_create_session(self, request: AgentRequest) -> AgentSession:
        if request.session_id is not None:
            existing = await self._sessions.get(request.tenant_id, request.session_id)
            if existing is not None:
                return existing
        return await self._sessions.insert(
            AgentSession(
                id=uuid.uuid4(),
                tenant_id=request.tenant_id,
                machine_id=request.machine_id,
                incident_id=request.incident_id,
                maintenance_case_id=request.maintenance_case_id,
            )
        )

    async def _record_tool_call(
        self,
        tenant_id: uuid.UUID,
        session: AgentSession,
        result: ToolResult,
        correlation_id: str,
    ) -> None:
        # `arguments` is never persisted here — only `result.summary`/`status`, which are
        # already short, human-readable, and contain no telemetry payloads or secrets
        # (Phase 19 brief §19.10).
        await self._tool_calls.insert(
            AgentToolCall(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                session_id=session.id,
                tool_name=result.tool_name,
                arguments={},
                status=result.status,
                result_summary=result.summary,
                correlation_id=correlation_id,
            )
        )

    async def _persist_assistant_message(
        self, tenant_id: uuid.UUID, session: AgentSession, response: AgentResponse
    ) -> None:
        await self._messages.insert(
            AgentMessage(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                content=response.answer,
                response_payload={
                    "citations": [dataclasses.asdict(c) for c in response.citations],
                    "tool_calls": [
                        {"tool_name": t.tool_name, "status": t.status, "summary": t.summary}
                        for t in response.tool_calls
                    ],
                    "draft_artifacts": [
                        {"kind": a.kind, "content": a.content} for a in response.draft_artifacts
                    ],
                    "limitations": list(response.limitations),
                    "human_review_required": response.human_review_required,
                },
            )
        )
