"""`KnowledgeChunk` repository — including the pgvector-backed similarity search that
`Retriever` builds on. The approved/tenant-visibility filter lives here, in the query
itself, not merely as an application-level convention — DRAFT/REVIEW/RETIRED chunks are
structurally unreachable by this method (Phase 18 brief §18.2/§18.8)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DocumentStatus
from app.domain.models import KnowledgeChunk, KnowledgeDocument


class KnowledgeChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_many(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        self.session.add_all(chunks)
        await self.session.flush()
        for chunk in chunks:
            await self.session.refresh(chunk)
        return chunks

    async def list_for_document(self, document_id: uuid.UUID) -> list[KnowledgeChunk]:
        result = await self.session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.ordinal)
        )
        return list(result.scalars().all())

    async def search_approved(
        self,
        tenant_id: uuid.UUID | None,
        query_embedding: list[float],
        *,
        document_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[tuple[KnowledgeChunk, KnowledgeDocument, float]]:
        """Returns `(chunk, document, cosine_distance)` tuples ordered by ascending
        cosine distance (closer = more similar), restricted to `APPROVED` documents
        visible to `tenant_id` (that tenant's own documents plus every global document —
        never another tenant's). `document_types`, if given, further restricts which
        `DocumentType`s are eligible (e.g. excluding `SERVICE_CASE` for a pure-procedure
        search, or restricting to only `SERVICE_CASE` for a similar-cases search)."""
        distance = KnowledgeChunk.embedding.cosine_distance(query_embedding)
        clauses = [
            KnowledgeDocument.status == DocumentStatus.APPROVED,
            (KnowledgeDocument.tenant_id == tenant_id) | (KnowledgeDocument.tenant_id.is_(None)),
        ]
        if document_types is not None:
            clauses.append(KnowledgeDocument.document_type.in_(document_types))

        stmt = (
            select(KnowledgeChunk, KnowledgeDocument, distance.label("distance"))
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(*clauses)
            .order_by(distance)
            .limit(min(limit, 100))
        )
        result = await self.session.execute(stmt)
        return list(result.tuples().all())
