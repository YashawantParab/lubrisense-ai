"""`KnowledgeService` — ingestion + document lifecycle (Phase 18 brief §18.1/§18.2/
§18.12). Deliberately combined in one orchestration service since both are thin wrappers
around `KnowledgeDocumentRepository`/`KnowledgeChunkRepository` with no independent
business logic worth splitting further — unlike the intelligence-layer engines, there is
no pure-function core here to keep separately testable (chunking/embedding are already
their own pure modules).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DocumentStatus
from app.domain.models import KnowledgeChunk, KnowledgeDocument
from app.knowledge.domain.models import DocumentDraft
from app.knowledge.embeddings.provider import EmbeddingProvider, HashingEmbeddingProvider
from app.knowledge.repositories.chunk_repository import KnowledgeChunkRepository
from app.knowledge.repositories.document_repository import KnowledgeDocumentRepository
from app.knowledge.services.chunking import chunk_markdown


class DocumentNotFoundError(LookupError):
    pass


class DocumentVersionConflictError(ValueError):
    def __init__(self, document_key: str, version: str) -> None:
        super().__init__(
            f"Document {document_key}@{version} already exists with different content."
        )


class InvalidDocumentTransitionError(ValueError):
    def __init__(self, current: DocumentStatus, target: DocumentStatus) -> None:
        super().__init__(f"Cannot transition document from {current.value} to {target.value}.")


_VALID_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.DRAFT: frozenset({DocumentStatus.REVIEW}),
    DocumentStatus.REVIEW: frozenset({DocumentStatus.APPROVED, DocumentStatus.DRAFT}),
    DocumentStatus.APPROVED: frozenset({DocumentStatus.RETIRED}),
    DocumentStatus.RETIRED: frozenset(),
}


class KnowledgeService:
    def __init__(
        self, session: AsyncSession, embedding_provider: EmbeddingProvider | None = None
    ) -> None:
        self._session = session
        self._documents = KnowledgeDocumentRepository(session)
        self._chunks = KnowledgeChunkRepository(session)
        self._embeddings = embedding_provider or HashingEmbeddingProvider()

    async def ingest(self, draft: DocumentDraft) -> KnowledgeDocument:
        """Deterministic, idempotent (Phase 18 brief §18.15): ingesting the exact same
        `(document_key, version, content)` twice returns the already-persisted row
        rather than creating a duplicate; a genuinely different `content` under the same
        `(document_key, version)` is rejected outright rather than silently overwritten."""
        checksum = hashlib.sha256(draft.content.encode("utf-8")).hexdigest()
        existing = await self._documents.get_by_key_and_version(
            draft.tenant_id, draft.document_key, draft.version
        )
        if existing is not None:
            if existing.checksum == checksum:
                return existing
            raise DocumentVersionConflictError(draft.document_key, draft.version)

        document = KnowledgeDocument(
            id=uuid.uuid4(),
            tenant_id=draft.tenant_id,
            document_key=draft.document_key,
            title=draft.title,
            document_type=draft.document_type,
            version=draft.version,
            status=DocumentStatus.DRAFT,
            content=draft.content,
            source_name=draft.source_name,
            effective_date=draft.effective_date,
            approved_at=None,
            approved_by=None,
            checksum=checksum,
        )
        document = await self._documents.insert(document)

        chunk_drafts = chunk_markdown(draft.content)
        chunks = [
            KnowledgeChunk(
                id=uuid.uuid4(),
                document_id=document.id,
                ordinal=c.ordinal,
                section=c.section,
                heading=c.heading,
                content=c.content,
                character_count=c.character_count,
                embedding=self._embeddings.embed(f"{draft.title}. {c.heading}. {c.content}"),
            )
            for c in chunk_drafts
        ]
        if chunks:
            await self._chunks.insert_many(chunks)
        return document

    async def get(self, document_id: uuid.UUID) -> KnowledgeDocument:
        document = await self._documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError(str(document_id))
        return document

    async def list_documents(
        self,
        tenant_id: uuid.UUID | None,
        *,
        status: DocumentStatus | None = None,
        document_type: str | None = None,
        limit: int = 200,
    ) -> list[KnowledgeDocument]:
        return await self._documents.list_for_tenant(
            tenant_id, status=status, document_type=document_type, limit=limit
        )

    async def submit_for_review(self, document_id: uuid.UUID) -> KnowledgeDocument:
        return await self._transition(document_id, DocumentStatus.REVIEW)

    async def approve(self, document_id: uuid.UUID, *, approved_by: str) -> KnowledgeDocument:
        """Transitions REVIEW -> APPROVED. If a different version of the same
        `(tenant_id, document_key)` is currently APPROVED, it is transitioned to RETIRED
        in the same operation — supersede, never delete (Phase 18 brief §18.12, ADR-121's
        pattern applied to documents).

        The "find the prior APPROVED version" lookup must happen BEFORE this document is
        itself marked APPROVED — doing it after would momentarily leave two rows
        APPROVED for the same key at once, which `get_approved()`'s `scalar_one_or_none`
        cannot represent (a real bug caught live: `MultipleResultsFound`)."""
        document = await self.get(document_id)
        if DocumentStatus.APPROVED not in _VALID_TRANSITIONS.get(document.status, frozenset()):
            raise InvalidDocumentTransitionError(document.status, DocumentStatus.APPROVED)

        prior = await self._documents.get_approved(document.tenant_id, document.document_key)

        document.status = DocumentStatus.APPROVED
        document.approved_at = datetime.now(UTC)
        document.approved_by = approved_by
        document = await self._documents.save(document)

        if prior is not None and prior.id != document.id:
            prior.status = DocumentStatus.RETIRED
            await self._documents.save(prior)

        return document

    async def retire(self, document_id: uuid.UUID) -> KnowledgeDocument:
        return await self._transition(document_id, DocumentStatus.RETIRED)

    async def _transition(
        self, document_id: uuid.UUID, target: DocumentStatus
    ) -> KnowledgeDocument:
        document = await self.get(document_id)
        if target not in _VALID_TRANSITIONS.get(document.status, frozenset()):
            raise InvalidDocumentTransitionError(document.status, target)
        document.status = target
        return await self._documents.save(document)
