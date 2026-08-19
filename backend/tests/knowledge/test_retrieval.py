"""Database integration: `Retriever`/`RAGService` — approved-only retrieval, lifecycle
exclusion, tenant isolation, citations, insufficient-documentation, and service-case
distinction (Phase 18 brief §18.8-§18.13/§18.15).

Every fixture below embeds a unique nonsense marker token (`zqfrobnitor...`) in both its
content and its query — this dev Postgres instance also carries the real, permanently-
seeded demo corpus (`app.knowledge.corpus.documents.CORPUS`), so tests must not assume
they are the only approved documents in the database; a rare, deterministic marker makes
every assertion exact regardless of what else is approved.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.domain.models import DocumentDraft
from app.knowledge.services.knowledge_service import KnowledgeService
from app.knowledge.services.rag_service import INSUFFICIENT_DOCUMENTATION_TEXT, RAGService
from app.knowledge.services.retriever import Retriever
from tests.factories import make_tenant

_MARKER = "zqfrobnitor"

_RESTRICTION_CONTENT = f"""# Distributor Restriction Guide {_MARKER}

## Inspection Steps

Visually inspect the {_MARKER} distributor housing and every outlet for a partially
blocked opening, a common finding for a developing restriction pattern.
"""

_SERVICE_CASE_CONTENT = f"""# Synthetic Service Case {_MARKER}

## Summary

A {_MARKER} developing restriction pattern was flagged. A partially blocked distributor
outlet was found and cleaned; the case closed TRUE_POSITIVE.
"""

_QUERY = f"{_MARKER} distributor restriction inspection"


async def _approved_document(session: AsyncSession, service: KnowledgeService, **overrides: object):
    base = {
        "document_key": f"retrieval-test-doc-{_MARKER}",
        "title": f"Distributor Restriction Guide {_MARKER}",
        "document_type": "TROUBLESHOOTING_GUIDE",
        "version": "1.0.0",
        "source_name": "Test",
        "content": _RESTRICTION_CONTENT,
        "tenant_id": None,
    }
    base.update(overrides)
    document = await service.ingest(DocumentDraft(**base))  # type: ignore[arg-type]
    await service.submit_for_review(document.id)
    return await service.approve(document.id, approved_by="tester")


@pytest.mark.asyncio
async def test_approved_document_is_retrieved(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    await _approved_document(db_session, service)
    retriever = Retriever(db_session)
    results = await retriever.search(None, _QUERY)
    assert len(results) >= 1
    assert results[0].citation.document_title == f"Distributor Restriction Guide {_MARKER}"


@pytest.mark.asyncio
async def test_draft_document_is_excluded(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    await service.ingest(
        DocumentDraft(
            document_key=f"draft-only-doc-{_MARKER}",
            title=f"Draft Only Doc {_MARKER}",
            document_type="TROUBLESHOOTING_GUIDE",
            version="1.0.0",
            source_name="Test",
            content=_RESTRICTION_CONTENT,
        )
    )
    retriever = Retriever(db_session)
    results = await retriever.search(None, _QUERY)
    assert all(f"Draft Only Doc {_MARKER}" != r.citation.document_title for r in results)


@pytest.mark.asyncio
async def test_review_document_is_excluded(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    document = await service.ingest(
        DocumentDraft(
            document_key=f"review-only-doc-{_MARKER}",
            title=f"Review Only Doc {_MARKER}",
            document_type="TROUBLESHOOTING_GUIDE",
            version="1.0.0",
            source_name="Test",
            content=_RESTRICTION_CONTENT,
        )
    )
    await service.submit_for_review(document.id)
    retriever = Retriever(db_session)
    results = await retriever.search(None, _QUERY)
    assert all(f"Review Only Doc {_MARKER}" != r.citation.document_title for r in results)


@pytest.mark.asyncio
async def test_retired_document_is_excluded(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    document = await _approved_document(db_session, service, document_key=f"retired-doc-{_MARKER}")
    await service.retire(document.id)
    retriever = Retriever(db_session)
    results = await retriever.search(None, _QUERY)
    assert all(
        f"Distributor Restriction Guide {_MARKER}" != r.citation.document_title for r in results
    )


@pytest.mark.asyncio
async def test_only_the_current_approved_version_is_retrieved(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    key = f"versioned-doc-{_MARKER}"
    v1 = await service.ingest(
        DocumentDraft(
            document_key=key,
            title=f"Versioned Guide V1 {_MARKER}",
            document_type="TROUBLESHOOTING_GUIDE",
            version="1.0.0",
            source_name="Test",
            content=_RESTRICTION_CONTENT,
        )
    )
    await service.submit_for_review(v1.id)
    await service.approve(v1.id, approved_by="tester")

    v2 = await service.ingest(
        DocumentDraft(
            document_key=key,
            title=f"Versioned Guide V2 {_MARKER}",
            document_type="TROUBLESHOOTING_GUIDE",
            version="2.0.0",
            source_name="Test",
            content=_RESTRICTION_CONTENT,
        )
    )
    await service.submit_for_review(v2.id)
    await service.approve(v2.id, approved_by="tester")

    retriever = Retriever(db_session)
    results = await retriever.search(None, _QUERY)
    titles = {r.citation.document_title for r in results}
    assert f"Versioned Guide V2 {_MARKER}" in titles
    assert f"Versioned Guide V1 {_MARKER}" not in titles


@pytest.mark.asyncio
async def test_tenant_scoped_document_is_isolated(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    service = KnowledgeService(db_session)
    await _approved_document(
        db_session, service, document_key=f"tenant-a-doc-{_MARKER}", tenant_id=tenant_a.id
    )
    retriever = Retriever(db_session)

    results_a = await retriever.search(tenant_a.id, _QUERY)
    results_b = await retriever.search(tenant_b.id, _QUERY)
    title = f"Distributor Restriction Guide {_MARKER}"
    assert any(r.citation.document_title == title for r in results_a)
    assert all(r.citation.document_title != title for r in results_b)


@pytest.mark.asyncio
async def test_global_document_is_visible_to_every_tenant(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    service = KnowledgeService(db_session)
    await _approved_document(db_session, service, tenant_id=None)
    retriever = Retriever(db_session)
    results = await retriever.search(tenant.id, _QUERY)
    assert any(
        r.citation.document_title == f"Distributor Restriction Guide {_MARKER}" for r in results
    )


@pytest.mark.asyncio
async def test_citation_correctness(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    document = await _approved_document(db_session, service)
    retriever = Retriever(db_session)
    results = await retriever.search(None, _QUERY)
    citation = results[0].citation
    assert citation.document_id == str(document.id)
    assert citation.document_version == "1.0.0"
    assert citation.heading == "Inspection Steps"
    assert citation.section == "Inspection Steps"


@pytest.mark.asyncio
async def test_insufficient_documentation_exact_response(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    await _approved_document(db_session, service)
    rag = RAGService(db_session)
    answer = await rag.answer(None, "quantum entanglement stock market forecast")
    assert answer.status == "INSUFFICIENT"
    assert answer.text == INSUFFICIENT_DOCUMENTATION_TEXT
    assert answer.citations == ()


@pytest.mark.asyncio
async def test_insufficient_for_a_query_with_no_matching_approved_evidence(
    db_session: AsyncSession,
) -> None:
    """Even with the real demo corpus present, a query matching nothing approved must
    still return the exact insufficient-documentation response — never a fallback."""
    rag = RAGService(db_session)
    answer = await rag.answer(None, f"{_MARKER} completely unrelated nonsense topic xyzzy")
    assert answer.status == "INSUFFICIENT"
    assert answer.text == INSUFFICIENT_DOCUMENTATION_TEXT


@pytest.mark.asyncio
async def test_service_cases_are_distinguished_from_procedures(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    await _approved_document(db_session, service, document_key=f"procedure-doc-{_MARKER}")
    case_document = await service.ingest(
        DocumentDraft(
            document_key=f"service-case-doc-{_MARKER}",
            title=f"Synthetic Restriction Case {_MARKER}",
            document_type="SERVICE_CASE",
            version="1.0.0",
            source_name="Test",
            content=_SERVICE_CASE_CONTENT,
        )
    )
    await service.submit_for_review(case_document.id)
    await service.approve(case_document.id, approved_by="tester")

    rag = RAGService(db_session)
    answer = await rag.answer(None, _QUERY)
    assert len(answer.procedure_results) >= 1
    assert len(answer.service_case_results) >= 1
    assert all(r.citation.document_type != "SERVICE_CASE" for r in answer.procedure_results)
    assert all(r.citation.document_type == "SERVICE_CASE" for r in answer.service_case_results)
    assert "similar synthetic service case" in answer.text.lower()
