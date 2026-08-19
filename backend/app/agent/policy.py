"""The guarded-agent's explicit system policy (Phase 19 brief §19.7) plus deterministic
intent classification (`classify_intent`) and the physical-control refusal boundary.

`classify_intent` runs ONLY on the raw user message, never on retrieved document content
— this is the structural core of the prompt-injection defense (§19.18): a document chunk
returned by `search_approved_documentation`/`search_similar_service_cases` is placed into
`AgentResponse.citations`/composed answer text as quoted data, but it is never re-parsed
by this module to decide intent, tools, or the human-review boundary. Retrieved text
cannot authorize a tool, and it cannot change what tools were already decided before
retrieval ran.
"""

from __future__ import annotations

import re

SYSTEM_POLICY = """The assistant:
- explains persisted intelligence (ConditionAssessment, DecisionAssessment,
  PrognosticAssessment, Incident, MaintenanceCase) as source of truth, never its own
  diagnosis
- retrieves approved knowledge (Phase 18) and cites it
- drafts workflow artifacts (checklist, work-order draft, investigation notes) — always
  clearly labeled DRAFT, never executed
- assists human investigation

The assistant does not:
- diagnose independently or override a persisted ConditionAssessment/DecisionAssessment
- control machinery, issue control commands, or change machinery configuration
- create unverified facts, or record a technician finding as fact on a human's behalf
- bypass human review (acknowledge/close incidents, complete maintenance cases, submit
  external CMMS work orders, retrain/promote ML models)
- claim production certainty it does not have
"""

_PHYSICAL_CONTROL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bstop\b.{0,20}\b(machine|pump|conveyor|motor|equipment)\b",
        r"\b(shut|power)\s*down\b",
        r"\bturn\s*off\b",
        r"\breset\s+the\s+controller\b",
        r"\brestart\s+the\s+(pump|controller|machine)\b",
        r"\bdisable\s+(the\s+)?(interlock|safety|controller)\b",
        r"\boverride\s+(the\s+)?(controller|plc|interlock|safety)\b",
        r"\bactuate\b",
        r"\benergi[sz]e\b",
        r"\bchange\s+the\s+lubrication\s+quantity\b",
        r"\bissue\s+a\s+control\s+command\b",
    )
]

PHYSICAL_CONTROL_REFUSAL = (
    "I can't stop, reset, or otherwise control machinery — that requires direct human "
    "action on-site, following your normal safety procedure. I can help with "
    "informational workflow assistance instead: explaining the current condition and "
    "decision, retrieving approved inspection guidance, or preparing a draft checklist "
    "or work order for a technician to review."
)

_CHECKLIST_PATTERNS = [re.compile(r"\bchecklist\b", re.IGNORECASE)]
_WORK_ORDER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in (r"\bwork[\s-]?order\b", r"\bcmms\b")
]


def is_physical_control_request(message: str) -> bool:
    return any(pattern.search(message) for pattern in _PHYSICAL_CONTROL_PATTERNS)


def wants_checklist_draft(message: str) -> bool:
    return any(pattern.search(message) for pattern in _CHECKLIST_PATTERNS)


def wants_work_order_draft(message: str) -> bool:
    return any(pattern.search(message) for pattern in _WORK_ORDER_PATTERNS)


def classify_intent(message: str) -> str:
    """One of `PHYSICAL_CONTROL`, `CHECKLIST_DRAFT`, `WORK_ORDER_DRAFT`, `GENERAL`. Only
    ever reads the raw user message."""
    if is_physical_control_request(message):
        return "PHYSICAL_CONTROL"
    if wants_work_order_draft(message):
        return "WORK_ORDER_DRAFT"
    if wants_checklist_draft(message):
        return "CHECKLIST_DRAFT"
    return "GENERAL"
