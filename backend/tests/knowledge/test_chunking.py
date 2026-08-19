"""Pure deterministic-chunking tests (Phase 18 brief §18.6)."""

from __future__ import annotations

from app.knowledge.services.chunking import chunk_markdown

SAMPLE = """# Sample Document

## First Section

This is the first section's real content, long enough to be kept as a chunk.

## Second Section

This is the second section's real content, also long enough to be kept.
"""


def test_chunks_split_by_heading() -> None:
    chunks = chunk_markdown(SAMPLE)
    assert [c.heading for c in chunks] == ["First Section", "Second Section"]


def test_chunks_are_ordinal_and_sequential() -> None:
    chunks = chunk_markdown(SAMPLE)
    assert [c.ordinal for c in chunks] == [0, 1]


def test_chunking_is_deterministic() -> None:
    assert chunk_markdown(SAMPLE) == chunk_markdown(SAMPLE)


def test_title_line_is_not_a_chunk() -> None:
    chunks = chunk_markdown(SAMPLE)
    assert all(c.heading != "Sample Document" for c in chunks)


def test_tiny_section_is_dropped() -> None:
    content = """# Doc

## Real Section

This is a real, sufficiently long section body for a real chunk.

## Tiny

x
"""
    chunks = chunk_markdown(content)
    assert [c.heading for c in chunks] == ["Real Section"]


def test_character_count_matches_content_length() -> None:
    chunks = chunk_markdown(SAMPLE)
    for chunk in chunks:
        assert chunk.character_count == len(chunk.content)


def test_empty_document_produces_no_chunks() -> None:
    assert chunk_markdown("") == []
