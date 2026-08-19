"""Pure embedding/lexical-scoring tests (Phase 18 brief §18.7/§18.8)."""

from __future__ import annotations

from app.domain.models import _EMBEDDING_DIMENSIONS
from app.knowledge.embeddings.provider import (
    EMBEDDING_DIMENSIONS,
    HashingEmbeddingProvider,
    lexical_overlap_score,
)

PROVIDER = HashingEmbeddingProvider()


def test_embedding_dimension_matches_column() -> None:
    """Pins `app.knowledge.embeddings.provider.EMBEDDING_DIMENSIONS` and
    `app.domain.models._EMBEDDING_DIMENSIONS` together — see both modules' comments."""
    assert EMBEDDING_DIMENSIONS == _EMBEDDING_DIMENSIONS


def test_embedding_is_deterministic() -> None:
    text = "Inspect the distributor for a partially blocked outlet."
    assert PROVIDER.embed(text) == PROVIDER.embed(text)


def test_embedding_has_correct_dimension() -> None:
    assert len(PROVIDER.embed("some text")) == EMBEDDING_DIMENSIONS


def test_embedding_of_empty_text_is_zero_vector() -> None:
    assert PROVIDER.embed("") == [0.0] * EMBEDDING_DIMENSIONS


def test_embedding_is_l2_normalized() -> None:
    import math

    vector = PROVIDER.embed("developing restriction pattern pressure flow")
    norm = math.sqrt(sum(v * v for v in vector))
    assert abs(norm - 1.0) < 1e-9


def test_different_texts_produce_different_embeddings() -> None:
    assert PROVIDER.embed("distributor blockage") != PROVIDER.embed("reservoir leakage")


def test_lexical_overlap_full_match() -> None:
    assert (
        lexical_overlap_score("distributor blockage", "the distributor blockage was found") == 1.0
    )


def test_lexical_overlap_no_match() -> None:
    assert lexical_overlap_score("distributor blockage", "unrelated bearing vibration") == 0.0


def test_lexical_overlap_ignores_stopwords() -> None:
    """A query that is entirely stopwords plus one real word should only count the real
    word — this is what makes the retrieval relevance gate work for genuinely off-topic
    queries (see `Retriever.search`)."""
    assert lexical_overlap_score("what is the distributor", "distributor housing") == 1.0


def test_lexical_overlap_all_stopwords_is_zero() -> None:
    assert lexical_overlap_score("what is the", "distributor housing") == 0.0
