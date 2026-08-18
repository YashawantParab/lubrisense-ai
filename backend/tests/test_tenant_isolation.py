"""Critical cross-tenant isolation tests (LOOP.md §34).

Every repository query is scoped by tenant_id in addition to the composite-tenant-FK
schema (defense in depth — see TECHNICAL_DECISIONS.md). These tests prove the service
layer actually enforces it, not just that the schema could.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.customer_account_service import CustomerAccountService
from app.services.errors import NotFoundError
from app.services.machine_service import MachineService
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
)


@pytest.mark.asyncio
async def test_tenant_cannot_retrieve_another_tenants_customer(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    customer_b = await make_customer(db_session, tenant_b)

    service = CustomerAccountService(db_session)

    with pytest.raises(NotFoundError):
        await service.get(tenant_a.id, customer_b.id)

    # Sanity check: tenant_b can retrieve its own customer.
    found = await service.get(tenant_b.id, customer_b.id)
    assert found.id == customer_b.id


@pytest.mark.asyncio
async def test_tenant_cannot_retrieve_another_tenants_machine(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)

    customer_b = await make_customer(db_session, tenant_b)
    site_b = await make_site(db_session, tenant_b, customer_b)
    plant_b = await make_plant(db_session, tenant_b, site_b)
    line_b = await make_production_line(db_session, tenant_b, plant_b)
    machine_b = await make_machine(db_session, tenant_b, line_b)

    service = MachineService(db_session)

    with pytest.raises(NotFoundError):
        await service.get(tenant_a.id, machine_b.id)


@pytest.mark.asyncio
async def test_tenant_cannot_retrieve_another_tenants_machine_hierarchy(
    db_session: AsyncSession,
) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)

    customer_b = await make_customer(db_session, tenant_b)
    site_b = await make_site(db_session, tenant_b, customer_b)
    plant_b = await make_plant(db_session, tenant_b, site_b)
    line_b = await make_production_line(db_session, tenant_b, plant_b)
    machine_b = await make_machine(db_session, tenant_b, line_b)

    service = MachineService(db_session)

    with pytest.raises(NotFoundError):
        await service.get_hierarchy(tenant_a.id, machine_b.id)


@pytest.mark.asyncio
async def test_tenant_customer_list_excludes_other_tenants(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    await make_customer(db_session, tenant_a)
    await make_customer(db_session, tenant_b)
    await make_customer(db_session, tenant_b)

    service = CustomerAccountService(db_session)

    page_a = await service.list(tenant_a.id)
    page_b = await service.list(tenant_b.id)

    assert page_a.total == 1
    assert page_b.total == 2
    assert {c.tenant_id for c in page_a.items} == {tenant_a.id}
    assert {c.tenant_id for c in page_b.items} == {tenant_b.id}
