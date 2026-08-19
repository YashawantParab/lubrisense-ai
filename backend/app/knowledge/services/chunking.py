"""Deterministic markdown-heading chunking (Phase 18 brief §18.6). Pure — no I/O.

Documents in this corpus follow a simple convention: an optional `# Title` line, then one
or more `## Heading` sections. Each `##` section becomes exactly one `ChunkDraft` —
never an arbitrary character-count split — so a citation's `heading`/`section` always
names a real, meaningful part of the source document, and section hierarchy is preserved
end to end.
"""

from __future__ import annotations

from app.knowledge.domain.models import ChunkDraft

_MIN_SECTION_CHARACTERS = 20


def chunk_markdown(content: str) -> list[ChunkDraft]:
    lines = content.strip().splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_heading is not None:
                sections.append((current_heading, current_lines))
            current_heading = stripped[3:].strip()
            current_lines = []
        elif stripped.startswith("# "):
            # Document title line — not a chunk boundary on its own.
            continue
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections.append((current_heading, current_lines))

    chunks: list[ChunkDraft] = []
    for ordinal, (heading, body_lines) in enumerate(sections):
        body = "\n".join(body_lines).strip()
        if len(body) < _MIN_SECTION_CHARACTERS:
            # A near-empty section is not useful, citable evidence on its own — never
            # persist an arbitrary tiny fragment (Phase 18 brief §18.6).
            continue
        chunks.append(
            ChunkDraft(
                ordinal=ordinal,
                section=heading,
                heading=heading,
                content=body,
            )
        )
    return chunks
