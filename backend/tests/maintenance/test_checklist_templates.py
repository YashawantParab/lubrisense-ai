"""Pure checklist-template resolution tests (Phase 17 brief §17.5)."""

from __future__ import annotations

from app.domain.enums import RecommendedAction
from app.maintenance.checklist_templates import (
    CHECKLIST_TEMPLATES,
    DEFAULT_TEMPLATE_ID,
    resolve_checklist,
)


def test_every_recommended_action_has_a_template() -> None:
    """A silently-missing template would leave a maintenance case with an empty
    checklist for a real recommended action."""
    for action in RecommendedAction:
        assert action.value in CHECKLIST_TEMPLATES, action.value


def test_resolve_known_action_returns_its_template() -> None:
    template_id, items = resolve_checklist("INSPECT_LUBRICATION_PATH")
    assert template_id == "INSPECT_LUBRICATION_PATH"
    assert len(items) > 0
    assert all(isinstance(item, str) for item in items)


def test_resolve_unknown_action_falls_back_to_generic_template() -> None:
    template_id, items = resolve_checklist("NOT_A_REAL_ACTION")
    assert template_id == DEFAULT_TEMPLATE_ID
    assert len(items) > 0


def test_every_template_item_is_safety_conscious_generic_text() -> None:
    """No proprietary/company-specific wording — demo templates only (CLAUDE.md)."""
    banned_terms = ("proprietary", "confidential", "internal use only")
    for items in CHECKLIST_TEMPLATES.values():
        for item in items:
            lowered = item.lower()
            assert not any(term in lowered for term in banned_terms)
