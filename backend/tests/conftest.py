"""Shared test fixtures.

These are integration tests: they exercise the real FastAPI app against real Postgres and
Redis instances (see `docker-compose.yml` / `infrastructure/`), not mocks. Run
`docker compose up -d postgres redis` (or the full stack) before `pytest` — see
docs/DEVELOPER_SETUP.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models import Tenant
from app.infrastructure.database import Database
from app.main import create_app
from tests.factories import make_tenant


@pytest.fixture
def client() -> Iterator[TestClient]:
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def api_tenant() -> AsyncIterator[Tenant]:
    """A committed (not rolled back) tenant for tests that go through `client` — a
    TestClient request uses its own session via `get_db_session`, which commits, so it
    cannot see an uncommitted tenant from the `db_session` fixture's transaction.
    """
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            await session.commit()
            yield tenant
    finally:
        await database.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session scoped to one uncommitted transaction, rolled back after the test.

    Repositories/services only ever `flush()`, never `commit()` (commits happen in the
    API's `get_db_session` dependency, or in the seed script's own `main()`) — so any
    test using only this fixture leaves zero residue in the database, regardless of how
    much it creates.
    """
    database = Database(get_settings())
    try:
        async with database.session() as session:
            yield session
            await session.rollback()
    finally:
        await database.dispose()
