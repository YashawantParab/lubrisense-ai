"""Pure `DemoLLMProvider` composition tests."""

from __future__ import annotations

from app.agent.providers.llm_provider import DemoLLMProvider
from app.knowledge.services.rag_service import INSUFFICIENT_DOCUMENTATION_TEXT

PROVIDER = DemoLLMProvider()


def test_empty_evidence_is_insufficient_text() -> None:
    assert PROVIDER.compose_answer(intent="GENERAL", evidence={}) == INSUFFICIENT_DOCUMENTATION_TEXT


def test_condition_is_quoted_verbatim_never_invented() -> None:
    evidence = {
        "condition": {
            "condition_type": "DEVELOPING_RESTRICTION_PATTERN",
            "severity": "WARNING",
            "confidence": "MODERATE",
            "what_is_happening": "Test evidence text.",
        }
    }
    answer = PROVIDER.compose_answer(intent="GENERAL", evidence=evidence)
    assert "Developing Restriction Pattern" in answer
    assert "Test evidence text." in answer


def test_decision_recommended_action_is_quoted_verbatim() -> None:
    evidence = {
        "decision": {
            "recommended_action": "INSPECT_LUBRICATION_PATH",
            "priority": "PLANNED",
            "recommended_window": "NEXT_PLANNED_MAINTENANCE",
            "risk_if_deferred": "Test risk text.",
        }
    }
    answer = PROVIDER.compose_answer(intent="GENERAL", evidence=evidence)
    assert "Inspect Lubrication Path" in answer
    assert "Test risk text." in answer


def test_insufficient_rag_status_with_no_results_includes_exact_text() -> None:
    evidence = {"procedure_results": [], "rag_status": "INSUFFICIENT"}
    answer = PROVIDER.compose_answer(intent="GENERAL", evidence=evidence)
    assert INSUFFICIENT_DOCUMENTATION_TEXT in answer


def test_procedure_results_are_labeled_as_approved_guidance() -> None:
    evidence = {
        "procedure_results": [
            {"document_title": "Test Doc", "heading": "Steps", "excerpt": "Do the thing."}
        ]
    }
    answer = PROVIDER.compose_answer(intent="GENERAL", evidence=evidence)
    assert "approved guidance" in answer.lower()
    assert "Test Doc" in answer


def test_service_case_results_are_labeled_as_similar_not_mandatory() -> None:
    evidence = {
        "service_case_results": [{"document_title": "Case One", "excerpt": "Something happened."}]
    }
    answer = PROVIDER.compose_answer(intent="GENERAL", evidence=evidence)
    assert "similar synthetic service case" in answer.lower()


def test_checklist_draft_artifact_is_labeled_draft() -> None:
    evidence = {
        "draft_artifacts": [
            {
                "kind": "CHECKLIST_DRAFT",
                "content": {"items": [{"text": "Inspect the thing.", "completed": False}]},
            }
        ]
    }
    answer = PROVIDER.compose_answer(intent="CHECKLIST_DRAFT", evidence=evidence)
    assert "DRAFT" in answer
    assert "not executed" in answer.lower()


def test_work_order_draft_artifact_is_labeled_draft() -> None:
    evidence = {
        "draft_artifacts": [
            {
                "kind": "WORK_ORDER_DRAFT",
                "content": {"external_reference": "DEMO-WO-TEST"},
            }
        ]
    }
    answer = PROVIDER.compose_answer(intent="WORK_ORDER_DRAFT", evidence=evidence)
    assert "DRAFT" in answer
    assert "not submitted externally" in answer.lower()
    assert "DEMO-WO-TEST" in answer


_MULTI_EVIDENCE = {
    "condition": {
        "condition_type": "DEVELOPING_RESTRICTION_PATTERN",
        "severity": "HIGH",
        "confidence": "HIGH",
        "what_is_happening": "Test condition text.",
    },
    "decision": {
        "recommended_action": "INSPECT_LUBRICATION_PATH",
        "priority": "URGENT",
        "recommended_window": "NOW",
        "risk_if_deferred": "Test risk text.",
    },
}


def test_differently_phrased_questions_lead_with_different_sections() -> None:
    """Regression test: within GENERAL intent, every question previously produced
    byte-identical output regardless of what was actually asked (compose_answer
    discarded `intent` and never saw the raw message at all) — a real repetitive-answer
    defect, not a false impression. Same underlying facts, different emphasis/ordering
    based on the real question."""
    why_answer = PROVIDER.compose_answer(
        intent="GENERAL", evidence=_MULTI_EVIDENCE, message="Why is this happening?"
    )
    action_answer = PROVIDER.compose_answer(
        intent="GENERAL", evidence=_MULTI_EVIDENCE, message="What should I do about it?"
    )

    assert why_answer != action_answer
    assert why_answer.startswith("Current condition")
    assert action_answer.startswith("Recommended action")
    # No fact is ever added or dropped by reordering — both sections still present in both.
    for answer in (why_answer, action_answer):
        assert "Developing Restriction Pattern" in answer
        assert "Inspect Lubrication Path" in answer


def test_unrecognized_question_keeps_the_original_default_order() -> None:
    """No `message` (or a message matching no known focus keyword) must produce the
    exact same output as before this change — existing callers that don't pass `message`
    must see no behavior change."""
    with_default = PROVIDER.compose_answer(intent="GENERAL", evidence=_MULTI_EVIDENCE)
    with_unmatched = PROVIDER.compose_answer(
        intent="GENERAL", evidence=_MULTI_EVIDENCE, message="hello there"
    )
    assert with_default == with_unmatched
    assert with_default.startswith("Current condition")
