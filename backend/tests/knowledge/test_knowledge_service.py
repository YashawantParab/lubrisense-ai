"""Database integration: `KnowledgeService` — ingestion idempotency, lifecycle
transitions, and version supersession (Phase 18 brief §18.2/§18.12/§18.15)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DocumentStatus
from app.knowledge.domain.models import DocumentDraft
from app.knowledge.services.knowledge_service import (
    DocumentNotFoundError,
    DocumentVersionConflictError,
    InvalidDocumentTransitionError,
    KnowledgeService,
)

_CONTENT = """# Test Doc

## Section One

Real content for section one, long enough to be kept as a chunk.
"""


def _draft(**overrides: object) -> DocumentDraft:
    base = {
        "document_key": "test-doc",
        "title": "Test Doc",
        "document_type": "SERVICE_PROCEDURE",
        "version": "1.0.0",
        "source_name": "Test Source",
        "content": _CONTENT,
        "tenant_id": None,
    }
    base.update(overrides)
    return DocumentDraft(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ingest_creates_a_draft_document(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    document = await service.ingest(_draft())
    assert document.status == DocumentStatus.DRAFT
    assert document.checksum


@pytest.mark.asyncio
async def test_ingest_same_content_twice_is_idempotent(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    first = await service.ingest(_draft())
    second = await service.ingest(_draft())
    assert first.id == second.id


@pytest.mark.asyncio
async def test_ingest_same_key_version_different_content_conflicts(
    db_session: AsyncSession,
) -> None:
    service = KnowledgeService(db_session)
    await service.ingest(_draft())
    with pytest.raises(DocumentVersionConflictError):
        await service.ingest(_draft(content=_CONTENT + "\n## Extra\n\nMore real content here.\n"))


@pytest.mark.asyncio
async def test_full_lifecycle_draft_review_approved(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    document = await service.ingest(_draft())
    reviewed = await service.submit_for_review(document.id)
    assert reviewed.status == DocumentStatus.REVIEW
    approved = await service.approve(document.id, approved_by="tester")
    assert approved.status == DocumentStatus.APPROVED
    assert approved.approved_by == "tester"
    assert approved.approved_at is not None


@pytest.mark.asyncio
async def test_cannot_approve_a_draft_directly(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    document = await service.ingest(_draft())
    with pytest.raises(InvalidDocumentTransitionError):
        await service.approve(document.id, approved_by="tester")


@pytest.mark.asyncio
async def test_approving_a_new_version_retires_the_prior_approved_version(
    db_session: AsyncSession,
) -> None:
    service = KnowledgeService(db_session)
    v1 = await service.ingest(_draft(version="1.0.0"))
    await service.submit_for_review(v1.id)
    await service.approve(v1.id, approved_by="tester")

    v2 = await service.ingest(_draft(version="2.0.0"))
    await service.submit_for_review(v2.id)
    await service.approve(v2.id, approved_by="tester")

    refreshed_v1 = await service.get(v1.id)
    refreshed_v2 = await service.get(v2.id)
    assert refreshed_v1.status == DocumentStatus.RETIRED
    assert refreshed_v2.status == DocumentStatus.APPROVED


@pytest.mark.asyncio
async def test_retire_an_approved_document(db_session: AsyncSession) -> None:
    service = KnowledgeService(db_session)
    document = await service.ingest(_draft())
    await service.submit_for_review(document.id)
    await service.approve(document.id, approved_by="tester")
    retired = await service.retire(document.id)
    assert retired.status == DocumentStatus.RETIRED


@pytest.mark.asyncio
async def test_get_unknown_document_raises(db_session: AsyncSession) -> None:
    import uuid

    service = KnowledgeService(db_session)
    with pytest.raises(DocumentNotFoundError):
        await service.get(uuid.uuid4())


@pytest.mark.asyncio
async def test_ingest_creates_real_chunks(db_session: AsyncSession) -> None:
    from app.knowledge.repositories.chunk_repository import KnowledgeChunkRepository

    service = KnowledgeService(db_session)
    document = await service.ingest(_draft())
    chunks = await KnowledgeChunkRepository(db_session).list_for_document(document.id)
    assert len(chunks) == 1
    assert chunks[0].heading == "Section One"
