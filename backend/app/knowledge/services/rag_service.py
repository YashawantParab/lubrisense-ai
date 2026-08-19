"""`RAGService` — composes a cited, approved-only answer from `Retriever` results (Phase
18 brief §18.9/§18.10/§18.13). No LLM here — this is deterministic retrieval-plus-
composition; Phase 19's agent is the layer that adds LLM-orchestrated conversation on top
of this grounded, testable foundation.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DocumentType
from app.knowledge.config.policy import KnowledgePolicy, load_knowledge_policy
from app.knowledge.domain.models import RAGAnswer, RetrievalResult
from app.knowledge.services.retriever import Retriever

#: The one required exact response (Phase 18 brief §18.10) — never paraphrased, never
#: replaced with a fallback to general model knowledge.
INSUFFICIENT_DOCUMENTATION_TEXT = "Insufficient approved documentation to answer reliably."


def _compose_text(
    procedure_results: tuple[RetrievalResult, ...],
    service_case_results: tuple[RetrievalResult, ...],
) -> str:
    parts: list[str] = []
    if procedure_results:
        parts.append("Relevant approved guidance:")
        for result in procedure_results:
            parts.append(
                f"— {result.citation.document_title} ({result.citation.section}): {result.excerpt}"
            )
    if service_case_results:
        # Phase 18 brief §18.13: a similar historical case is evidence of what happened
        # once, never presented as mandatory procedure.
        parts.append("\nA similar synthetic service case recorded:")
        for result in service_case_results:
            parts.append(f"— {result.citation.document_title}: {result.excerpt}")
    return "\n".join(parts)


class RAGService:
    def __init__(
        self,
        session: AsyncSession,
        policy: KnowledgePolicy | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        self._policy = policy or load_knowledge_policy()
        self._retriever = retriever or Retriever(session, self._policy)

    async def answer(self, tenant_id: uuid.UUID | None, query: str) -> RAGAnswer:
        results = await self._retriever.search(tenant_id, query, limit=self._policy.max_results)
        if not results:
            return RAGAnswer(status="INSUFFICIENT", text=INSUFFICIENT_DOCUMENTATION_TEXT)

        top_score = results[0].score
        if top_score < self._policy.partial_min_score:
            return RAGAnswer(status="INSUFFICIENT", text=INSUFFICIENT_DOCUMENTATION_TEXT)

        status = "SUFFICIENT" if top_score >= self._policy.sufficient_min_score else "PARTIAL"
        procedure_results = tuple(
            r for r in results if r.citation.document_type != DocumentType.SERVICE_CASE.value
        )
        service_case_results = tuple(
            r for r in results if r.citation.document_type == DocumentType.SERVICE_CASE.value
        )
        if not procedure_results and not service_case_results:
            return RAGAnswer(status="INSUFFICIENT", text=INSUFFICIENT_DOCUMENTATION_TEXT)

        text = _compose_text(procedure_results, service_case_results)
        citations = tuple(r.citation for r in results)
        return RAGAnswer(
            status=status,
            text=text,
            citations=citations,
            procedure_results=procedure_results,
            service_case_results=service_case_results,
        )
