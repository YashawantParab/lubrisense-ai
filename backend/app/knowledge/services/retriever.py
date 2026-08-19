"""`Retriever` — approved-only semantic + lexical retrieval (Phase 18 brief §18.8)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.config.policy import KnowledgePolicy, load_knowledge_policy
from app.knowledge.domain.models import Citation, RetrievalResult
from app.knowledge.embeddings.provider import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    lexical_overlap_score,
)
from app.knowledge.repositories.chunk_repository import KnowledgeChunkRepository

_CANDIDATE_POOL = 20


class Retriever:
    def __init__(
        self,
        session: AsyncSession,
        policy: KnowledgePolicy | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._chunks = KnowledgeChunkRepository(session)
        self._policy = policy or load_knowledge_policy()
        self._embeddings = embedding_provider or HashingEmbeddingProvider()

    async def search(
        self,
        tenant_id: uuid.UUID | None,
        query: str,
        *,
        document_types: list[str] | None = None,
        limit: int | None = None,
    ) -> list[RetrievalResult]:
        query_embedding = self._embeddings.embed(query)
        rows = await self._chunks.search_approved(
            tenant_id, query_embedding, document_types=document_types, limit=_CANDIDATE_POOL
        )

        scored: list[tuple[float, RetrievalResult]] = []
        for chunk, document, distance in rows:
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            lexical = lexical_overlap_score(
                query, f"{document.title}. {chunk.heading}. {chunk.content}"
            )
            if lexical == 0.0:
                # `HashingEmbeddingProvider` is a crude bag-of-words proxy, not a real
                # semantic model (docs/RAG_KNOWLEDGE_SYSTEM.md "Embedding strategy") — a
                # nonzero cosine similarity with ZERO literal shared vocabulary is not
                # trustworthy evidence of relevance at this implementation's fidelity, so
                # such a candidate is excluded outright rather than scored. This is what
                # makes a genuinely off-topic query correctly return no results (and
                # therefore INSUFFICIENT) instead of a spuriously "similar" document.
                continue
            score = (
                self._policy.similarity_weight * similarity + self._policy.lexical_weight * lexical
            )
            result = RetrievalResult(
                citation=Citation(
                    document_id=str(document.id),
                    document_title=document.title,
                    document_version=document.version,
                    document_type=document.document_type.value,
                    section=chunk.section,
                    heading=chunk.heading,
                    chunk_id=str(chunk.id),
                ),
                excerpt=chunk.content,
                score=score,
            )
            scored.append((score, result))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_n = limit or self._policy.max_results
        return [result for _score, result in scored[:top_n]]
