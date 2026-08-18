"""Service-layer validation: parent existence, tenant scoping of that check, retired
parents blocking new child creation, and duplicate-code conflicts."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MachineType, OperationalStatus, ServiceTier
from app.services.customer_account_service import CustomerAccountCreate, CustomerAccountService
from app.services.errors import ConflictError, InvalidHierarchyError
from app.services.machine_service import MachineCreate, MachineService
from app.services.plant_service import PlantCreate, PlantService
from app.services.production_line_service import ProductionLineCreate, ProductionLineService
from app.services.site_service import SiteCreate, SiteService
from tests.factories import (
    make_customer,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
    unique,
)


@pytest.mark.asyncio
async def test_site_create_rejects_unknown_customer(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    service = SiteService(db_session)

    with pytest.raises(InvalidHierarchyError):
        await service.create(
            tenant.id,
            SiteCreate(customer_account_id=uuid.uuid4(), name="Ghost Site", code=unique("SITE")),
        )


@pytest.mark.asyncio
async def test_site_create_rejects_customer_from_another_tenant(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    customer_b = await make_customer(db_session, tenant_b)

    service = SiteService(db_session)

    with pytest.raises(InvalidHierarchyError):
        await service.create(
            tenant_a.id,
            SiteCreate(customer_account_id=customer_b.id, name="Cross Site", code=unique("SITE")),
        )


@pytest.mark.asyncio
async def test_plant_create_rejects_decommissioned_site(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    site.status = OperationalStatus.DECOMMISSIONED
    await db_session.flush()

    service = PlantService(db_session)

    with pytest.raises(InvalidHierarchyError):
        await service.create(
            tenant.id, PlantCreate(site_id=site.id, name="Doomed Plant", code=unique("PLANT"))
        )


@pytest.mark.asyncio
async def test_production_line_duplicate_code_within_plant_conflicts(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)

    service = ProductionLineService(db_session)
    shared_code = unique("LINE")
    await service.create(
        tenant.id, ProductionLineCreate(plant_id=plant.id, name="First Line", code=shared_code)
    )

    with pytest.raises(ConflictError):
        await service.create(
            tenant.id, ProductionLineCreate(plant_id=plant.id, name="Second Line", code=shared_code)
        )


@pytest.mark.asyncio
async def test_machine_duplicate_asset_code_conflicts(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)

    service = MachineService(db_session)
    shared_asset_code = unique("ASSET")
    await service.create(
        tenant.id,
        MachineCreate(
            production_line_id=line.id,
            name="Machine One",
            asset_code=shared_asset_code,
            machine_type=MachineType.MOTOR,
        ),
    )

    with pytest.raises(ConflictError):
        await service.create(
            tenant.id,
            MachineCreate(
                production_line_id=line.id,
                name="Machine Two",
                asset_code=shared_asset_code,
                machine_type=MachineType.MOTOR,
            ),
        )


@pytest.mark.asyncio
async def test_customer_account_duplicate_code_conflicts(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    service = CustomerAccountService(db_session)
    shared_code = unique("CUST")

    await service.create(
        tenant.id,
        CustomerAccountCreate(
            name="First Customer", code=shared_code, service_tier=ServiceTier.CONNECTED_MONITORING
        ),
    )

    with pytest.raises(ConflictError):
        await service.create(
            tenant.id,
            CustomerAccountCreate(
                name="Second Customer",
                code=shared_code,
                service_tier=ServiceTier.CONNECTED_MONITORING,
            ),
        )
