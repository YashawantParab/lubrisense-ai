#!/usr/bin/env python3
"""Seeds the approved knowledge corpus (`app.knowledge.corpus.seed.seed_corpus`) so the
Knowledge and Assistant pages have real, APPROVED documents to retrieve/cite from.
Idempotent — `KnowledgeService.ingest()` is keyed by `document_key`, so re-running this
never creates duplicates.

Usage:
    uv run python scripts/seed_knowledge_corpus.py
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.infrastructure.database import Database
from app.knowledge.corpus.seed import seed_corpus

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed_knowledge_corpus")


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    try:
        async with database.session() as session:
            created = await seed_corpus(session)
            await session.commit()
    finally:
        await database.dispose()

    if created:
        logger.info("Ingested %d new approved document(s).", created)
    else:
        logger.info("Nothing to ingest — knowledge corpus already seeded (idempotent no-op).")


if __name__ == "__main__":
    asyncio.run(main())
