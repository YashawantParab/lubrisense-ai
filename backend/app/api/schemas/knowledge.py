"""Phase 18 knowledge/RAG API contracts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import DocumentType


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    document_key: str
    title: str
    document_type: str
    version: str
    status: str
    source_name: str
    effective_date: date | None
    approved_at: datetime | None
    approved_by: str | None
    created_at: datetime


class IngestDocumentRequest(BaseModel):
    document_key: str
    title: str
    document_type: DocumentType
    version: str
    source_name: str
    content: str
    effective_date: date | None = None


class ApproveDocumentRequest(BaseModel):
    approved_by: str = "demo-reviewer"


class CitationResponse(BaseModel):
    document_id: str
    document_title: str
    document_version: str
    document_type: str
    section: str
    heading: str
    chunk_id: str


class RetrievalResultResponse(BaseModel):
    citation: CitationResponse
    excerpt: str
    score: float


class SearchRequest(BaseModel):
    query: str
    document_types: list[DocumentType] | None = None
    limit: int | None = None


class AnswerRequest(BaseModel):
    query: str


class RAGAnswerResponse(BaseModel):
    status: str
    text: str
    citations: list[CitationResponse]
    procedure_results: list[RetrievalResultResponse]
    service_case_results: list[RetrievalResultResponse]
