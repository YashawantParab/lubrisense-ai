"""Tenant-scoped Phase 18 approved-knowledge API. Only `APPROVED` documents ever enter
retrieval/answer results — see docs/RAG_KNOWLEDGE_SYSTEM.md "Purpose"."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_app_settings, get_current_tenant, get_db_session, require_permission
from app.api.schemas.knowledge import (
    AnswerRequest,
    ApproveDocumentRequest,
    CitationResponse,
    IngestDocumentRequest,
    KnowledgeDocumentResponse,
    RAGAnswerResponse,
    RetrievalResultResponse,
    SearchRequest,
)
from app.audit.service import AuditActor, AuditService
from app.auth.models import Principal
from app.auth.permissions import Permission
from app.core.config import Settings
from app.domain.enums import DocumentStatus
from app.domain.models import Tenant
from app.knowledge.domain.models import DocumentDraft
from app.knowledge.observability import METRICS
from app.knowledge.services.knowledge_service import (
    DocumentNotFoundError,
    DocumentVersionConflictError,
    InvalidDocumentTransitionError,
    KnowledgeService,
)
from app.knowledge.services.rag_service import RAGService
from app.knowledge.services.retriever import Retriever

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/metrics")
async def get_knowledge_metrics() -> Response:
    """Registered before `/documents/{document_id}` so the literal path `metrics` is
    never mistaken for a document id."""
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
async def list_documents(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status_: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    document_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[KnowledgeDocumentResponse]:
    service = KnowledgeService(session)
    documents = await service.list_documents(
        tenant.id, status=status_, document_type=document_type, limit=limit
    )
    return [KnowledgeDocumentResponse.model_validate(d) for d in documents]


@router.post(
    "/documents", response_model=KnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED
)
async def ingest_document(
    body: IngestDocumentRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.KNOWLEDGE_ADMIN)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> KnowledgeDocumentResponse:
    """Ingests a new DRAFT document (or returns the existing row if the exact same
    `(document_key, version, content)` was already ingested — idempotent)."""
    if len(body.content) > settings.knowledge_document_max_content_length:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Document content exceeds the maximum allowed length.",
        )
    service = KnowledgeService(session)
    try:
        document = await service.ingest(
            DocumentDraft(
                document_key=body.document_key,
                title=body.title,
                document_type=body.document_type.value,
                version=body.version,
                source_name=body.source_name,
                content=body.content,
                tenant_id=tenant.id,
                effective_date=body.effective_date,
            )
        )
    except DocumentVersionConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    METRICS.increment("knowledge_documents_ingested")
    await AuditService(session).record(
        tenant.id,
        actor=AuditActor.from_principal(principal),
        action="KNOWLEDGE_DOCUMENT_INGESTED",
        entity_type="knowledge_document",
        entity_id=document.id,
        source="api.knowledge",
        after_summary=f"{document.document_key} v{document.version} ({document.status.value}).",
    )
    return KnowledgeDocumentResponse.model_validate(document)


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeDocumentResponse:
    del tenant
    service = KnowledgeService(session)
    try:
        document = await service.get(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.") from exc
    return KnowledgeDocumentResponse.model_validate(document)


async def _transition_or_error(coro: object) -> KnowledgeDocumentResponse:
    try:
        document = await coro  # type: ignore[misc]
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.") from exc
    except InvalidDocumentTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return KnowledgeDocumentResponse.model_validate(document)


async def _audit_document(
    session: AsyncSession,
    tenant: Tenant,
    principal: Principal,
    document_id: uuid.UUID,
    action: str,
    reason: str | None = None,
) -> None:
    await AuditService(session).record(
        tenant.id,
        actor=AuditActor.from_principal(principal),
        action=action,
        entity_type="knowledge_document",
        entity_id=document_id,
        source="api.knowledge",
        reason=reason,
    )


@router.post("/documents/{document_id}/submit-for-review", response_model=KnowledgeDocumentResponse)
async def submit_for_review(
    document_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.KNOWLEDGE_ADMIN)],
) -> KnowledgeDocumentResponse:
    service = KnowledgeService(session)
    response = await _transition_or_error(service.submit_for_review(document_id))
    await _audit_document(session, tenant, principal, document_id, "KNOWLEDGE_DOCUMENT_SUBMITTED")
    return response


@router.post("/documents/{document_id}/approve", response_model=KnowledgeDocumentResponse)
async def approve_document(
    document_id: uuid.UUID,
    body: ApproveDocumentRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.KNOWLEDGE_ADMIN)],
) -> KnowledgeDocumentResponse:
    service = KnowledgeService(session)
    response = await _transition_or_error(
        service.approve(document_id, approved_by=body.approved_by)
    )
    await _audit_document(
        session, tenant, principal, document_id, "KNOWLEDGE_DOCUMENT_APPROVED",
        reason=f"approved_by={body.approved_by}",
    )
    return response


@router.post("/documents/{document_id}/retire", response_model=KnowledgeDocumentResponse)
async def retire_document(
    document_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.KNOWLEDGE_ADMIN)],
) -> KnowledgeDocumentResponse:
    service = KnowledgeService(session)
    response = await _transition_or_error(service.retire(document_id))
    await _audit_document(session, tenant, principal, document_id, "KNOWLEDGE_DOCUMENT_RETIRED")
    return response


@router.post("/search", response_model=list[RetrievalResultResponse])
async def search(
    body: SearchRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[RetrievalResultResponse]:
    retriever = Retriever(session)
    document_types = [dt.value for dt in body.document_types] if body.document_types else None
    results = await retriever.search(
        tenant.id, body.query, document_types=document_types, limit=body.limit
    )
    return [
        RetrievalResultResponse(
            citation=CitationResponse(**dataclasses.asdict(r.citation)),
            excerpt=r.excerpt,
            score=r.score,
        )
        for r in results
    ]


@router.post("/answer", response_model=RAGAnswerResponse)
async def answer(
    body: AnswerRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RAGAnswerResponse:
    rag = RAGService(session)
    result = await rag.answer(tenant.id, body.query)
    METRICS.increment("knowledge_answers_generated")
    if result.status == "INSUFFICIENT":
        METRICS.increment("knowledge_answers_insufficient")
    return RAGAnswerResponse(
        status=result.status,
        text=result.text,
        citations=[CitationResponse(**dataclasses.asdict(c)) for c in result.citations],
        procedure_results=[
            RetrievalResultResponse(
                citation=CitationResponse(**dataclasses.asdict(r.citation)),
                excerpt=r.excerpt,
                score=r.score,
            )
            for r in result.procedure_results
        ],
        service_case_results=[
            RetrievalResultResponse(
                citation=CitationResponse(**dataclasses.asdict(r.citation)),
                excerpt=r.excerpt,
                score=r.score,
            )
            for r in result.service_case_results
        ],
    )
