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
    def compose_answer(
        self, *, intent: str, evidence: dict[str, Any], message: str = ""
    ) -> str: ...


# Which evidence section to foreground first, keyed by a coarse guess at what the raw
# question is actually asking about — `classify_intent` only distinguishes
# PHYSICAL_CONTROL/CHECKLIST_DRAFT/WORK_ORDER_DRAFT/GENERAL, so within GENERAL every
# question previously produced byte-identical output regardless of what was asked (a real
# demo-experience defect, not a routing concern). This never changes which facts are
# included — only which already-gathered, already-real section leads the answer — so the
# "never adds a fact that wasn't in evidence" guarantee is unaffected.
_FOCUS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "decision": ("should i do", "should we do", "recommend", "what to do", "next step", "action"),
    "condition": ("why", "happening", "cause", "diagnos", "evidence"),
    "maintenance_case": ("maintenance", "checklist", "technician", "work order"),
    "incident": ("incident",),
}
_DEFAULT_ORDER = (
    "condition",
    "decision",
    "incident",
    "maintenance_case",
    "procedure",
    "service_case",
    "draft",
)
_FOCUS_ORDER_OVERRIDES: dict[str, tuple[str, ...]] = {
    focus: (focus, *(key for key in _DEFAULT_ORDER if key != focus)) for focus in _FOCUS_KEYWORDS
}


def _focus_for(message: str) -> str | None:
    lowered = message.lower()
    for focus, keywords in _FOCUS_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return focus
    return None


class DemoLLMProvider:
    """Deterministic, dependency-free, no external call — see module docstring."""

    def compose_answer(self, *, intent: str, evidence: dict[str, Any], message: str = "") -> str:
        del intent
        sections: dict[str, str] = {}

        condition = evidence.get("condition")
        if condition:
            sections["condition"] = (
                f"What is happening: {condition['condition_type']} "
                f"({condition['severity']}, confidence {condition['confidence']}). "
                f"{condition['what_is_happening']}"
            )

        decision = evidence.get("decision")
        if decision:
            sections["decision"] = (
                f"What you should do: {decision['recommended_action']} "
                f"(priority {decision['priority']}, window {decision['recommended_window']}). "
                f"{decision['risk_if_deferred']}"
            )

        incident = evidence.get("incident")
        if incident:
            sections["incident"] = (
                f"Incident: {incident['title']} — currently {incident['state']} "
                f"({incident['severity']}/{incident['priority']})."
            )

        maintenance_case = evidence.get("maintenance_case")
        if maintenance_case:
            sections["maintenance_case"] = (
                f"Maintenance case state: {maintenance_case['state']} "
                f"(recommended action: {maintenance_case['recommended_action']})."
            )

        procedure_results = evidence.get("procedure_results") or []
        rag_status = evidence.get("rag_status")
        if procedure_results:
            excerpts = "; ".join(
                f"{r['document_title']} ({r['heading']}): {r['excerpt']}" for r in procedure_results
            )
            sections["procedure"] = f"Relevant approved guidance: {excerpts}"
        elif rag_status == "INSUFFICIENT":
            sections["procedure"] = INSUFFICIENT_DOCUMENTATION_TEXT

        service_case_results = evidence.get("service_case_results") or []
        if service_case_results:
            excerpts = "; ".join(
                f"{r['document_title']}: {r['excerpt']}" for r in service_case_results
            )
            sections["service_case"] = f"A similar synthetic service case recorded: {excerpts}"

        draft_artifacts = evidence.get("draft_artifacts") or []
        draft_parts: list[str] = []
        for artifact in draft_artifacts:
            if artifact["kind"] == "CHECKLIST_DRAFT":
                draft_parts.append(
                    "Checklist draft prepared (DRAFT only, not executed): "
                    + "; ".join(item["text"] for item in artifact["content"]["items"])
                )
            elif artifact["kind"] == "WORK_ORDER_DRAFT":
                draft_parts.append(
                    f"Work order draft prepared (DRAFT only, not submitted externally): "
                    f"{artifact['content']['external_reference']}."
                )
        if draft_parts:
            sections["draft"] = "\n\n".join(draft_parts)

        if not sections:
            return INSUFFICIENT_DOCUMENTATION_TEXT

        order = _FOCUS_ORDER_OVERRIDES.get(_focus_for(message) or "", _DEFAULT_ORDER)
        ordered = [sections[key] for key in order if key in sections]
        # Safety net, not expected to trigger: any section key `order` doesn't cover would
        # otherwise be silently dropped rather than just not being prioritized.
        ordered += [sections[key] for key in sections if key not in order]
        return "\n\n".join(ordered)
