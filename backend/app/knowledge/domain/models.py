"""Pure dataclasses for the knowledge package — no I/O, no SQLAlchemy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """One deterministically-chunked section of a document, before persistence."""

    ordinal: int
    section: str
    heading: str
    content: str

    @property
    def character_count(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class Citation:
    document_id: str
    document_title: str
    document_version: str
    document_type: str
    section: str
    heading: str
    chunk_id: str


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    citation: Citation
    excerpt: str
    score: float


@dataclass(frozen=True, slots=True)
class RAGAnswer:
    status: str  # RetrievalSufficiency value
    text: str
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    procedure_results: tuple[RetrievalResult, ...] = field(default_factory=tuple)
    service_case_results: tuple[RetrievalResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DocumentDraft:
    """Input to `KnowledgeIngestionService.ingest()` — a document not yet persisted."""

    document_key: str
    title: str
    document_type: str
    version: str
    source_name: str
    content: str
    tenant_id: uuid.UUID | None = None
    effective_date: date | None = None
