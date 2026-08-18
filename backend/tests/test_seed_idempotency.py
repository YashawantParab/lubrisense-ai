"""Proves scripts/seed_demo_data.py can run twice without duplicating data.

Runs the real `seed()` coroutine against the `db_session` fixture's uncommitted
transaction — `seed()` only ever `flush()`es (see get_or_create), so this leaves no trace
in the database regardless of whether the demo dataset was already seeded for real.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Machine, Sensor, Tenant
from scripts.seed_demo_data import seed


async def _table_counts(session: AsyncSession) -> tuple[int, int, int]:
    tenants = await session.scalar(select(func.count()).select_from(Tenant))
    machines = await session.scalar(select(func.count()).select_from(Machine))
    sensors = await session.scalar(select(func.count()).select_from(Sensor))
    return tenants or 0, machines or 0, sensors or 0


@pytest.mark.asyncio
async def test_seed_demo_data_is_idempotent(db_session: AsyncSession) -> None:
    await seed(db_session)
    counts_after_first_run = await _table_counts(db_session)

    await seed(db_session)
    counts_after_second_run = await _table_counts(db_session)

    assert counts_after_first_run == counts_after_second_run
    _tenants, machines, sensors = counts_after_first_run
    assert machines >= 20
    assert sensors > 0
