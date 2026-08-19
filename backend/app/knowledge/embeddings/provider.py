"""`EmbeddingProvider` abstraction (Phase 18 brief §18.7) plus the one provider this
reference implementation actually uses: a deterministic, dependency-free hashing-trick
bag-of-words vectorizer.

Why not a real trained embedding model: a proper sentence-transformer model needs a
~100-500MB local install (`torch` + model weights) — heavyweight for the "keep it
practical on modest hardware" constraint this sprint operates under (Phase 19 brief
§Performance explicitly warns against a large local install; the same tradeoff applies
here), and a paid embedding API is explicitly prohibited. `HashingEmbeddingProvider`
requires no extra runtime dependency beyond the Python standard library and pgvector
(already a platform dependency), stays perfectly deterministic (ADR-138), and is honest
about what it is: it approximates lexical/keyword overlap, not deep semantic similarity —
entirely adequate for a small (~10-15 document), topically-distinct demo corpus where
each document covers a clearly different subject.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

#: Must match `app.domain.models._EMBEDDING_DIMENSIONS` — pinned together by
#: `tests/knowledge/test_embeddings.py::test_embedding_dimension_matches_column`.
EMBEDDING_DIMENSIONS = 256

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

#: Minimal English stopword list — excluded only from `lexical_overlap_score` (the
#: relevance-gating signal in `Retriever`), never from embedding input. Without this, a
#: totally unrelated query like "What is the meaning of life?" registers false lexical
#: overlap purely on "is"/"of"/"the", which would defeat the overlap gate's entire
#: purpose (excluding genuinely off-topic queries, `Retriever.search`).
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "should",
        "so",
        "than",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    }
)


class EmbeddingProvider(Protocol):
    """Any provider (this hashing one, or a real model later) implements exactly this —
    `KnowledgeIngestionService`/`Retriever` only ever depend on this protocol."""

    def embed(self, text: str) -> list[float]: ...


def _tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN_PATTERN.findall(text.lower()) if len(token) >= 2]


class HashingEmbeddingProvider:
    """Feature-hashing ("hashing trick") bag-of-words vectorizer — the same technique
    `sklearn.feature_extraction.text.HashingVectorizer` uses, reimplemented here without
    the scikit-learn dependency to keep this one small function fully deterministic and
    inspectable. Each token hashes to one of `EMBEDDING_DIMENSIONS` buckets with a
    deterministic +1/-1 sign (reduces hash-collision bias), summed by term frequency, then
    L2-normalized so cosine similarity is well-behaved."""

    dimensions = EMBEDDING_DIMENSIONS

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        tokens = _tokenize(text)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            return vector
        return [component / norm for component in vector]


def lexical_overlap_score(query: str, text: str) -> float:
    """Simple lexical scoring (Phase 18 brief §18.8, optional) — fraction of distinct,
    non-stopword query tokens also present in `text`. `Retriever` uses this as a hard
    relevance gate (zero overlap excludes a candidate outright), so stopwords are
    excluded here — otherwise a totally unrelated query would register false overlap on
    words like "is"/"the"/"of" alone."""
    query_tokens = {t for t in _tokenize(query) if t not in _STOPWORDS}
    if not query_tokens:
        return 0.0
    text_tokens = set(_tokenize(text))
    return len(query_tokens & text_tokens) / len(query_tokens)
