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

`narrative_sections()` below is deliberately NOT part of the `LLMProvider` seam — the
frontend's structured answer cards (Current condition / Recommendation / ...) are built
from `evidence` directly, deterministically, so they stay correct even if `LLMProvider`
is later swapped for a real model that only improves `answer`'s prose.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    "maintenance_case": ("maintenance", "checklist", "technician", "work order", "confirm"),
    "incident": ("incident", "what happened"),
    "fleet_attention": (
        "which machine",
        "which asset",
        "fleet",
        "need attention",
        "needs attention",
        "data quality",
        "pending",
        "eligible for",
        "automation blocked",
    ),
}
_DEFAULT_ORDER = (
    "fleet_attention",
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

#: The narrative sections a reviewer reads as "the story" — procedure/service_case
#: excerpts are real evidence too, but belong in the frontend's collapsed Sources list
#: (via `AgentResponse.citations`, already populated for both), not the primary answer,
#: once there is real narrative to lead with (see `build_sections` docstring).
NARRATIVE_KEYS = ("fleet_attention", "condition", "decision", "incident", "maintenance_case")

SECTION_LABELS: dict[str, str] = {
    "fleet_attention": "Fleet attention",
    "condition": "Current condition",
    "decision": "Recommendation",
    "incident": "Recent significant event",
    "maintenance_case": "Maintenance outcome",
}


def _focus_for(message: str) -> str | None:
    lowered = message.lower()
    for focus, keywords in _FOCUS_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return focus
    return None


def _human(value: object) -> str:
    return str(value).replace("_", " ").title()


def _ordered_keys(message: str) -> tuple[str, ...]:
    return _FOCUS_ORDER_OVERRIDES.get(_focus_for(message) or "", _DEFAULT_ORDER)


def build_sections(evidence: dict[str, Any]) -> dict[str, str]:
    """Every enum-shaped evidence value (`condition_type`, `severity`, `state`, ...) is
    humanized here — this text reaches either the primary chat prose or a structured
    answer card an external reviewer reads, so it follows the same "human meaning first,
    raw identifier only in technical detail" rule as the rest of the product. The raw
    values stay available unmodified in `evidence`/`tool_calls` for anyone who needs
    them."""
    sections: dict[str, str] = {}

    fleet = evidence.get("fleet_attention")
    if fleet:
        needs_attention = fleet.get("needs_attention") or []
        if not needs_attention:
            parts = ["No machines currently need attention across the monitored fleet."]
        else:
            listed = ", ".join(
                f"{r['machine_name']} ({_human(r['condition_type'])}, "
                f"{_human(r['severity'])} severity"
                + (
                    f", recommended: {_human(r['recommended_action'])}"
                    if r["recommended_action"]
                    else ""
                )
                + ")"
                for r in needs_attention[:5]
            )
            parts = [f"{len(needs_attention)} machine(s) need attention: {listed}."]
        data_quality_limited = fleet.get("data_quality_limited") or []
        if data_quality_limited:
            names = ", ".join(r["machine_name"] for r in data_quality_limited[:5])
            parts.append(
                f"{len(data_quality_limited)} machine(s) are data-quality limited: {names}."
            )
        pending_approval = fleet.get("pending_human_approval") or []
        if pending_approval:
            names = ", ".join(r["machine_name"] for r in pending_approval[:5])
            parts.append(
                f"{len(pending_approval)} machine(s) have a recommendation awaiting "
                f"human approval: {names}."
            )
        pending_maintenance = fleet.get("pending_maintenance") or []
        if pending_maintenance:
            names = ", ".join(
                f"{c['machine_name']} ({_human(c['recommended_action'])})"
                for c in pending_maintenance[:5]
                if c["machine_name"]
            )
            parts.append(f"{len(pending_maintenance)} maintenance case(s) pending: {names}.")
        sections["fleet_attention"] = " ".join(parts)

    condition = evidence.get("condition")
    if condition:
        sections["condition"] = (
            f"{_human(condition['condition_type'])} "
            f"({_human(condition['severity'])} severity, "
            f"{_human(condition['confidence']).lower()} confidence). "
            f"{condition['what_is_happening']}"
        )

    decision = evidence.get("decision")
    if decision:
        sections["decision"] = (
            f"{_human(decision['recommended_action'])} "
            f"({_human(decision['priority'])} priority, "
            f"{_human(decision['recommended_window']).lower()} window). "
            f"{decision['risk_if_deferred']}"
        )

    incident = evidence.get("incident")
    if incident:
        sections["incident"] = (
            f"{incident['title']} — currently "
            f"{_human(incident['state']).lower()} "
            f"({_human(incident['severity'])} severity, "
            f"{_human(incident['priority'])} priority)."
        )

    maintenance_case = evidence.get("maintenance_case")
    if maintenance_case:
        parts = [
            f"{_human(maintenance_case['state']).lower()} "
            f"(recommended action: {_human(maintenance_case['recommended_action'])})."
        ]
        if maintenance_case.get("latest_finding_observed_issue"):
            parts.append(f"Technician finding: {maintenance_case['latest_finding_observed_issue']}")
        if maintenance_case.get("feedback_classification"):
            classification = maintenance_case["feedback_classification"]
            confirmed = "confirmed" if classification == "TRUE_POSITIVE" else "not confirmed"
            parts.append(
                f"Diagnosis {confirmed} by maintenance ({_human(classification).lower()})."
            )
        sections["maintenance_case"] = " ".join(parts)

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
        excerpts = "; ".join(f"{r['document_title']}: {r['excerpt']}" for r in service_case_results)
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

    return sections


@dataclass(frozen=True, slots=True)
class NarrativeSection:
    key: str
    label: str
    text: str


def narrative_sections(evidence: dict[str, Any], message: str = "") -> tuple[NarrativeSection, ...]:
    """The structured pieces the frontend renders as distinct answer cards — deliberately
    only the narrative keys (never raw retrieved-document excerpts, which belong in
    Sources), in the same focus-aware order `compose_answer()` uses for its plain-text
    fallback."""
    sections = build_sections(evidence)
    order = _ordered_keys(message)
    keys = [k for k in order if k in sections and k in NARRATIVE_KEYS]
    keys += [k for k in sections if k in NARRATIVE_KEYS and k not in keys]
    return tuple(
        NarrativeSection(key=key, label=SECTION_LABELS[key], text=sections[key]) for key in keys
    )


def _labeled(key: str, text: str) -> str:
    """Structured `AnswerSection.text` stays label-free (the frontend card already shows
    `SECTION_LABELS[key]` as its title) — the plain-text `answer` fallback re-adds it
    inline so it stays readable on its own, e.g. for a real-LLM-provider swap or any
    consumer that only reads `answer`."""
    label = SECTION_LABELS.get(key)
    return f"{label}: {text}" if label else text


class DemoLLMProvider:
    """Deterministic, dependency-free, no external call — see module docstring."""

    def compose_answer(self, *, intent: str, evidence: dict[str, Any], message: str = "") -> str:
        del intent
        sections = build_sections(evidence)
        if not sections:
            return INSUFFICIENT_DOCUMENTATION_TEXT

        order = _ordered_keys(message)
        # Once there is real narrative to answer from, retrieved-document excerpts are
        # dropped from the primary prose (they still ground the answer via citations, for
        # the frontend's Sources section) — otherwise a simple "what is the current
        # condition?" question came back as a wall of unrelated approved-guidance text
        # tacked onto the real answer, which is not what was asked.
        if any(key in sections for key in NARRATIVE_KEYS):
            order = tuple(key for key in order if key not in ("procedure", "service_case"))
            sections = {k: v for k, v in sections.items() if k not in ("procedure", "service_case")}
            if not sections:
                return INSUFFICIENT_DOCUMENTATION_TEXT

        ordered = [_labeled(key, sections[key]) for key in order if key in sections]
        # Safety net, not expected to trigger: any section key `order` doesn't cover would
        # otherwise be silently dropped rather than just not being prioritized.
        ordered += [_labeled(key, sections[key]) for key in sections if key not in order]
        return "\n\n".join(ordered)
