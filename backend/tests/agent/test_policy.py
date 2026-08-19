"""Pure intent-classification / physical-control-refusal tests (Phase 19 brief
§19.3/§19.7/§19.20, "AGENT CONTROL-SAFETY TEST")."""

from __future__ import annotations

from app.agent.policy import classify_intent, is_physical_control_request


def test_stop_the_machine_is_physical_control() -> None:
    assert is_physical_control_request("Stop the machine and reset the controller.")


def test_shut_down_is_physical_control() -> None:
    assert is_physical_control_request("Please shut down the pump right now.")


def test_reset_controller_is_physical_control() -> None:
    assert is_physical_control_request("Reset the controller.")


def test_override_interlock_is_physical_control() -> None:
    assert is_physical_control_request("Override the safety interlock so I can proceed.")


def test_what_is_happening_is_not_physical_control() -> None:
    assert not is_physical_control_request("What is happening and what should I inspect?")


def test_why_was_this_incident_created_is_not_physical_control() -> None:
    assert not is_physical_control_request("Why was this incident created?")


def test_classify_intent_physical_control() -> None:
    assert classify_intent("Stop the machine and reset the controller.") == "PHYSICAL_CONTROL"


def test_classify_intent_checklist_draft() -> None:
    assert classify_intent("Can you generate a checklist for this case?") == "CHECKLIST_DRAFT"


def test_classify_intent_work_order_draft() -> None:
    assert classify_intent("Please draft a work order for this.") == "WORK_ORDER_DRAFT"


def test_classify_intent_general() -> None:
    assert classify_intent("What is happening and what should I inspect?") == "GENERAL"


def test_work_order_pattern_takes_priority_over_checklist_pattern() -> None:
    """A message mentioning both should still resolve to one clear intent — work order
    is checked first since it is the more specific artifact request."""
    assert classify_intent("Draft a work order and checklist for this case.") == "WORK_ORDER_DRAFT"
