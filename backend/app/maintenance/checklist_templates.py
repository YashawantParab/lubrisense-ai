"""Deterministic, template-based inspection checklists (Phase 17 brief §17.5). NOT RAG,
NOT an LLM — a plain lookup keyed by `RecommendedAction`. Generic, safety-conscious
wording; demo workflow templates, never proprietary industrial procedures (CLAUDE.md
"Physical Industrial Model" / "Synthetic ranges must be explicitly labelled as demo
assumptions")."""

from __future__ import annotations

CHECKLIST_TEMPLATES: dict[str, list[str]] = {
    "INSPECT_LUBRICATION_PATH": [
        "Visually inspect accessible lubrication lines and the distributor path.",
        "Verify reservoir availability and lubricant level.",
        "Inspect for obvious leakage along the delivery path.",
        "Verify delivery-path condition where it is safe to access.",
        "Record all observations, even if no issue is found.",
    ],
    "INSPECT_DISTRIBUTOR": [
        "Visually inspect the distributor housing and outlets.",
        "Check for a blocked or partially blocked outlet.",
        "Verify piston/valve movement where safely observable.",
        "Inspect connected lines for restriction or damage.",
        "Record all observations, even if no issue is found.",
    ],
    "CHECK_RESERVOIR": [
        "Inspect reservoir lubricant level against its expected range.",
        "Check for signs of abnormal depletion or contamination.",
        "Verify reservoir refill mechanism/access is unobstructed.",
        "Record all observations, even if no issue is found.",
    ],
    "CHECK_PUMP": [
        "Inspect pump operating status and any local indicators.",
        "Record observed pump condition (noise, vibration, temperature if available).",
        "Verify pump current/runtime against applicable local indicators.",
        "Record all observations, even if no issue is found.",
    ],
    "INSPECT_BEARING": [
        "Inspect accessible bearing condition.",
        "Record temperature/vibration observations where available.",
        "Check for visible signs of mechanical wear or damage.",
        "Record all observations, even if no issue is found.",
    ],
    "VERIFY_SENSOR": [
        "Verify sensor is physically connected and powered.",
        "Check for visible sensor damage or miswiring.",
        "Confirm recent readings are reaching the platform.",
        "Record all observations, even if no issue is found.",
    ],
    "REQUEST_ADDITIONAL_MEASUREMENT": [
        "Identify what additional measurement or evidence is needed.",
        "Record the reason more evidence is required before acting.",
    ],
    "SCHEDULE_MAINTENANCE": [
        "Confirm scope of scheduled maintenance against current evidence.",
        "Record any relevant observations ahead of the scheduled work.",
    ],
    "CONTINUE_MONITORING": [
        "No inspection action required — continue routine monitoring.",
    ],
}

DEFAULT_TEMPLATE_ID = "GENERIC_INSPECTION"
_DEFAULT_CHECKLIST = [
    "Visually inspect the affected component.",
    "Record observed condition and any anomalies.",
]


def resolve_checklist(recommended_action: str) -> tuple[str, list[str]]:
    """Returns `(template_id, checklist_items)`. Falls back to a generic template rather
    than raising, since a `MaintenanceCase` must always be creatable from a valid
    `RecommendedAction` — an unmapped action is a template-coverage gap, not a reason to
    fail case creation."""
    items = CHECKLIST_TEMPLATES.get(recommended_action)
    if items is None:
        return DEFAULT_TEMPLATE_ID, list(_DEFAULT_CHECKLIST)
    return recommended_action, list(items)
