"""`LLMProvider` abstraction (Phase 19 brief §19.8) plus `DemoLLMProvider`, the only
provider this reference implementation actually calls.

`DemoLLMProvider` is a deterministic template composer, not a real language model — it
never makes an external call and never requires an API key (Phase 19 brief §19.9: "Do not
require purchasing API credits... must pass locally without a paid external LLM"). It
composes `AgentResponse.answer` text directly and only from the real evidence
`AgentService` already gathered via allowlisted tools — it never adds a fact that wasn't
in that evidence. Intent classification and tool orchestration (the actual "guarded
agent" logic) live in `app.agent.policy`/`app.agent.services.agent_service`, not here —
`LLMProvider` is intentionally a narrow, swappable seam: a real provider would take the
exact same evidence dict and produce more fluent prose from it, never different facts.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.knowledge.services.rag_service import INSUFFICIENT_DOCUMENTATION_TEXT


class LLMProviderUnavailableError(RuntimeError):
    pass


class LLMProvider(Protocol):
    def compose_answer(self, *, intent: str, evidence: dict[str, Any]) -> str: ...


class DemoLLMProvider:
    """Deterministic, dependency-free, no external call — see module docstring."""

    def compose_answer(self, *, intent: str, evidence: dict[str, Any]) -> str:
        del intent
        parts: list[str] = []

        condition = evidence.get("condition")
        if condition:
            parts.append(
                f"What is happening: {condition['condition_type']} "
                f"({condition['severity']}, confidence {condition['confidence']}). "
                f"{condition['what_is_happening']}"
            )

        decision = evidence.get("decision")
        if decision:
            parts.append(
                f"What you should do: {decision['recommended_action']} "
                f"(priority {decision['priority']}, window {decision['recommended_window']}). "
                f"{decision['risk_if_deferred']}"
            )

        incident = evidence.get("incident")
        if incident:
            parts.append(
                f"Incident: {incident['title']} — currently {incident['state']} "
                f"({incident['severity']}/{incident['priority']})."
            )

        maintenance_case = evidence.get("maintenance_case")
        if maintenance_case:
            parts.append(
                f"Maintenance case state: {maintenance_case['state']} "
                f"(recommended action: {maintenance_case['recommended_action']})."
            )

        procedure_results = evidence.get("procedure_results") or []
        rag_status = evidence.get("rag_status")
        if procedure_results:
            excerpts = "; ".join(
                f"{r['document_title']} ({r['heading']}): {r['excerpt']}" for r in procedure_results
            )
            parts.append(f"Relevant approved guidance: {excerpts}")
        elif rag_status == "INSUFFICIENT":
            parts.append(INSUFFICIENT_DOCUMENTATION_TEXT)

        service_case_results = evidence.get("service_case_results") or []
        if service_case_results:
            excerpts = "; ".join(
                f"{r['document_title']}: {r['excerpt']}" for r in service_case_results
            )
            parts.append(f"A similar synthetic service case recorded: {excerpts}")

        draft_artifacts = evidence.get("draft_artifacts") or []
        for artifact in draft_artifacts:
            if artifact["kind"] == "CHECKLIST_DRAFT":
                parts.append(
                    "Checklist draft prepared (DRAFT only, not executed): "
                    + "; ".join(item["text"] for item in artifact["content"]["items"])
                )
            elif artifact["kind"] == "WORK_ORDER_DRAFT":
                parts.append(
                    f"Work order draft prepared (DRAFT only, not submitted externally): "
                    f"{artifact['content']['external_reference']}."
                )

        if not parts:
            return INSUFFICIENT_DOCUMENTATION_TEXT

        return "\n\n".join(parts)
