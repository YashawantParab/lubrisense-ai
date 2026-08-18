from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.customer_account import CustomerAccountRepository
from app.repositories.pagination import PageParams
from tests.factories import make_customer, make_tenant


@pytest.mark.asyncio
async def test_get_returns_none_for_wrong_tenant(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    customer_b = await make_customer(db_session, tenant_b)

    repo = CustomerAccountRepository(db_session)

    assert await repo.get(tenant_a.id, customer_b.id) is None
    assert await repo.get(tenant_b.id, customer_b.id) is not None


@pytest.mark.asyncio
async def test_list_pagination_respects_limit_and_offset(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    for _ in range(5):
        await make_customer(db_session, tenant)

    repo = CustomerAccountRepository(db_session)

    first_page = await repo.list(tenant.id, params=PageParams(limit=2, offset=0))
    second_page = await repo.list(tenant.id, params=PageParams(limit=2, offset=2))
    last_page = await repo.list(tenant.id, params=PageParams(limit=2, offset=4))

    assert first_page.total == 5
    assert len(first_page.items) == 2
    assert first_page.has_more is True
    assert len(second_page.items) == 2
    assert len(last_page.items) == 1
    assert last_page.has_more is False

    first_ids = {c.id for c in first_page.items}
    second_ids = {c.id for c in second_page.items}
    assert first_ids.isdisjoint(second_ids)


@pytest.mark.asyncio
async def test_get_by_code_is_tenant_scoped(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    customer_b = await make_customer(db_session, tenant_b)

    repo = CustomerAccountRepository(db_session)

    assert await repo.get_by_code(tenant_a.id, customer_b.code) is None
    assert await repo.get_by_code(tenant_b.id, customer_b.code) is not None
