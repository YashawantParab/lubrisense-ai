"""`KnowledgeDocument` repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DocumentStatus
from app.domain.models import KnowledgeDocument


class KnowledgeDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, document: KnowledgeDocument) -> KnowledgeDocument:
        self.session.add(document)
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def save(self, document: KnowledgeDocument) -> KnowledgeDocument:
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def get(self, document_id: uuid.UUID) -> KnowledgeDocument | None:
        result = await self.session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_by_key_and_version(
        self, tenant_id: uuid.UUID | None, document_key: str, version: str
    ) -> KnowledgeDocument | None:
        """Tenant-scoped (ADR-140) — two different tenants ingesting the same
        `document_key`/`version` must never collide; a global document
        (`tenant_id=None`) only matches another global ingest of the same key/version."""
        result = await self.session.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.document_key == document_key,
                KnowledgeDocument.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def get_approved(
        self, tenant_id: uuid.UUID | None, document_key: str
    ) -> KnowledgeDocument | None:
        """`.limit(1)` rather than `scalar_one_or_none()`, deliberately tolerant of more
        than one match: Postgres unique indexes never enforce uniqueness across NULL
        values (`uq_knowledge_document_active_approved` cannot protect global,
        `tenant_id IS NULL` documents at the database level for this reason — see
        ADR-139) — application-level ordering in `KnowledgeService.approve()` is what
        actually keeps this to one row in practice, but this read must never hard-fail
        if that invariant is ever violated."""
        result = await self.session.execute(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.document_key == document_key,
                KnowledgeDocument.status == DocumentStatus.APPROVED,
            )
            .order_by(KnowledgeDocument.approved_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self,
        tenant_id: uuid.UUID | None,
        *,
        status: DocumentStatus | None = None,
        document_type: str | None = None,
        limit: int = 200,
    ) -> list[KnowledgeDocument]:
        # A tenant sees its own tenant-scoped documents plus every global (tenant_id IS
        # NULL) document — never another tenant's tenant-scoped documents.
        clauses = [
            (KnowledgeDocument.tenant_id == tenant_id)
            if tenant_id is None
            else (
                (KnowledgeDocument.tenant_id == tenant_id) | (KnowledgeDocument.tenant_id.is_(None))
            )
        ]
        if status is not None:
            clauses.append(KnowledgeDocument.status == status)
        if document_type is not None:
            clauses.append(KnowledgeDocument.document_type == document_type)
        result = await self.session.execute(
            select(KnowledgeDocument)
            .where(*clauses)
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(min(limit, 1000))
        )
        return list(result.scalars().all())
