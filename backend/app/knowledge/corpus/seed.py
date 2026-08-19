"""Seeds the synthetic demo corpus (`app.knowledge.corpus.documents.CORPUS`) as global
(`tenant_id=None`), `APPROVED` documents — idempotent, safe to run repeatedly. Used by
the demo Docker deployment and by tests that need a real approved corpus."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DocumentStatus
from app.knowledge.corpus.documents import CORPUS
from app.knowledge.domain.models import DocumentDraft
from app.knowledge.services.knowledge_service import KnowledgeService


async def seed_corpus(session: AsyncSession) -> int:
    """Returns the number of documents newly ingested (0 on a fully-idempotent rerun)."""
    service = KnowledgeService(session)
    created = 0
    for entry in CORPUS:
        draft = DocumentDraft(
            document_key=entry.document_key,
            title=entry.title,
            document_type=entry.document_type,
            version=entry.version,
            source_name=entry.source_name,
            content=entry.content,
            tenant_id=None,
        )
        document = await service.ingest(draft)
        if document.status == DocumentStatus.DRAFT:
            created += 1
            await service.submit_for_review(document.id)
            await service.approve(document.id, approved_by="demo-corpus-seed")
    return created
