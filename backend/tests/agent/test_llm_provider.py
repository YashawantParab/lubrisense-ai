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
    assert "DEVELOPING_RESTRICTION_PATTERN" in answer
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
    assert "INSPECT_LUBRICATION_PATH" in answer
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
