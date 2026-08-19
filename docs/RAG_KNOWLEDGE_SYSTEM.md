# RAG Knowledge System — Phase 18

## Purpose

`app.knowledge` answers maintenance/reliability questions using **only approved,
traceable documentation** — never general model knowledge, never DRAFT/REVIEW/RETIRED
content. It is the knowledge substrate Phase 19's agent grounds on; it has no LLM of its
own (see "Answer composition" below).

## Document model

`KnowledgeDocument` (migration `1769715b3831`, uniqueness fixed in `0f3855b92037`) is a
root entity — not `TenantScopedMixin` — with a nullable `tenant_id`:
`tenant_id IS NULL` means globally visible to every tenant (the common case for generic
industrial procedures); a non-null `tenant_id` means visible only to that tenant plus
every global document (ADR-139). `KnowledgeChunk` never denormalizes its parent's
status/tenant — the retriever always joins to `KnowledgeDocument` for those.

## Document lifecycle

Four states (`DocumentStatus`): `DRAFT` → `REVIEW` → `APPROVED` → `RETIRED`. Only
`APPROVED` documents are ever retrievable — enforced structurally in the one retrieval
query itself (`KnowledgeChunkRepository.search_approved()`, ADR-138), not by convention.

## Document versioning

Multiple rows may share a `document_key` (a stable slug) with different `version`
values. Approving a new version transitions the previously-APPROVED version for the same
`(tenant_id, document_key)` to `RETIRED` in the same operation — supersede, never delete
(the same pattern `DecisionAssessment` established, ADR-121, applied to documents;
ordering details in ADR-142). Old versions are preserved for audit; retrieval only ever
returns the current `APPROVED` version.

## Document types

Seven types (`DocumentType`): `OPERATING_GUIDE`, `SERVICE_PROCEDURE`,
`TROUBLESHOOTING_GUIDE`, `COMPONENT_REFERENCE`, `FAULT_CODE_REFERENCE`, `SAFETY_NOTE`,
`SERVICE_CASE`. `SERVICE_CASE` is deliberately distinct — a synthetic historical case is
evidence of what happened once, never presented as mandatory procedure (ADR-141).

## Synthetic knowledge corpus

`app.knowledge.corpus.documents.CORPUS` — 15 small, high-quality, clearly-generic
documents (never hundreds of junk pages): lubrication-path inspection, distributor
restriction/blockage inspection, leakage inspection, pump-performance inspection,
reservoir/low-level handling, bearing-condition inspection, sensor verification,
data-quality troubleshooting, a generic maintenance safety boundary, a fault-pattern
reference, a component reference, and four synthetic historical service cases. Every
document is explicitly synthetic/generic industrial terminology — no proprietary
manuals. `app.knowledge.corpus.seed.seed_corpus()` ingests and approves the whole corpus
idempotently (global scope, `tenant_id=None`).

## Chunking strategy

Deterministic markdown-heading chunking (`app.knowledge.services.chunking.
chunk_markdown`) — one chunk per `##` section, never an arbitrary character-count split.
A near-empty section (<20 characters) is dropped rather than persisted as a
non-citable fragment. `heading`/`section` are preserved verbatim for citations.

## Embedding strategy

`HashingEmbeddingProvider` (`app.knowledge.embeddings.provider`) — a deterministic,
dependency-free feature-hashing ("hashing trick") bag-of-words vectorizer, 256
dimensions, L2-normalized. **Not** a trained semantic model: a real sentence-transformer
would need a ~100-500MB local install (`torch` + weights), heavyweight for this sprint's
practical-hardware constraint, and a paid embedding API is explicitly prohibited
(ADR-138). `EmbeddingProvider` is a `Protocol` — a real model could be swapped in later
without touching `Retriever`/`RAGService`.

Storage footprint: 256 × 4 bytes (float) ≈ 1KB per chunk vector; the full 15-document
demo corpus (~60 chunks) is well under 100KB of embedding storage — negligible at this
scale.

## Retrieval model

`Retriever.search()` — pgvector cosine-distance ordering (`KnowledgeChunk.embedding.
cosine_distance()`) over a candidate pool, re-scored by a weighted blend of cosine
similarity and lexical overlap (`knowledge_v1.yaml`: `similarity_weight`/
`lexical_weight`). A candidate with **zero** lexical overlap is excluded outright
regardless of embedding similarity — the hashing embedding alone is not a trustworthy
relevance signal at this fidelity, found via a real live bug (a totally unrelated query
scored `SUFFICIENT` on hash-vector noise alone) — see ADR-143.

## Retrieval sufficiency

`RetrievalSufficiency`: `SUFFICIENT` / `PARTIAL` / `INSUFFICIENT` — explainable
thresholds (`sufficient_min_score`/`partial_min_score`), never a fabricated confidence
percentage (Phase 18 brief §18.11).

## Citations

Every `RAGAnswer`/`RetrievalResult` carries a `Citation`: document title, version,
type, section, heading, and chunk id — never an unsupported free-form claim.

## Insufficient-documentation rule

`RAGService.answer()` returns exactly `"Insufficient approved documentation to answer
reliably."` whenever retrieval has no candidate passing the lexical-overlap gate, or the
top score is below `partial_min_score` — never a fallback to unsupported general
knowledge.

## Service-case retrieval

`RAGAnswer.procedure_results`/`.service_case_results` are two separate tuples;
`DemoLLMProvider` frames them with different language ("Relevant approved guidance" vs.
"A similar synthetic service case recorded") so a technician never mistakes one prior
case for mandatory procedure.

## Answer composition

`RAGService` composes `RAGAnswer.text` deterministically from retrieved excerpts — **no
LLM**. Phase 19's `DemoLLMProvider` builds on the same retrieval layer for
conversational answers; `app.knowledge` itself has no language-model dependency at all.

## API

- `GET /api/v1/knowledge/documents`, `GET .../{id}` — admin/browsing (all statuses)
- `POST /api/v1/knowledge/documents` — idempotent ingest (DRAFT)
- `POST .../{id}/submit-for-review`, `.../approve`, `.../retire`
- `POST /api/v1/knowledge/search` — approved-only retrieval
- `POST /api/v1/knowledge/answer` — cited, approved-only RAG answer
- `GET /api/v1/knowledge/metrics`

## Known limitations

`HashingEmbeddingProvider` approximates lexical/keyword overlap, not deep semantic
similarity — a query phrased with entirely different vocabulary than the approved
document will not retrieve it (ADR-143's accepted precision-over-recall tradeoff). No
IVFFlat/HNSW pgvector index — a plain sequential scan is appropriate at this corpus's
demo scale (dozens of chunks) and would need revisiting only at real-fleet document
volume.
