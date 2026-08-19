"""Database integration: `DemoCMMSAdapter` — draft creation, idempotency, get, and status
update (Phase 20 brief §20.2/§20.5)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.cmms.adapters.demo_adapter import DemoCMMSAdapter
from app.cmms.domain.adapter import WorkOrderDraftRequest
from app.domain.models import MaintenanceCase
from tests.cmms.helpers import seed_case
from tests.factories import make_tenant


def _request(case: MaintenanceCase) -> WorkOrderDraftRequest:
    return WorkOrderDraftRequest(
        maintenance_case_id=str(case.id),
        title="Inspect Lubrication Path — Test Machine",
        description="Draft work order for a synthetic demo case.",
        asset_reference="M-TEST-001",
        priority=case.priority.value,
        recommended_window=case.recommended_window.value,
        checklist=["Visually inspect the delivery path.", "Record observations."],
    )


@pytest.mark.asyncio
async def test_create_draft_generates_a_reference(db_session: AsyncSession) -> None:
    tenant, case = await seed_case(db_session)
    adapter = DemoCMMSAdapter(db_session, tenant.id)
    record = await adapter.create_work_order_draft(_request(case))
    assert record.external_reference.startswith("DEMO-WO-")
    assert record.status == "DRAFT"
    assert record.checklist == ["Visually inspect the delivery path.", "Record observations."]


@pytest.mark.asyncio
async def test_create_draft_is_idempotent_per_case(db_session: AsyncSession) -> None:
    """Phase 20 brief §20.5: never create multiple accidental drafts for the same case."""
    tenant, case = await seed_case(db_session)
    adapter = DemoCMMSAdapter(db_session, tenant.id)
    first = await adapter.create_work_order_draft(_request(case))
    second = await adapter.create_work_order_draft(_request(case))
    assert first.external_reference == second.external_reference


@pytest.mark.asyncio
async def test_different_cases_get_different_drafts(db_session: AsyncSession) -> None:
    tenant_a, case_a = await seed_case(db_session)
    tenant_b, case_b = await seed_case(db_session)
    first = await DemoCMMSAdapter(db_session, tenant_a.id).create_work_order_draft(_request(case_a))
    second = await DemoCMMSAdapter(db_session, tenant_b.id).create_work_order_draft(
        _request(case_b)
    )
    assert first.external_reference != second.external_reference


@pytest.mark.asyncio
async def test_get_work_order_returns_the_created_draft(db_session: AsyncSession) -> None:
    tenant, case = await seed_case(db_session)
    adapter = DemoCMMSAdapter(db_session, tenant.id)
    created = await adapter.create_work_order_draft(_request(case))
    fetched = await adapter.get_work_order(created.external_reference)
    assert fetched is not None
    assert fetched.external_reference == created.external_reference


@pytest.mark.asyncio
async def test_get_unknown_work_order_returns_none(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    adapter = DemoCMMSAdapter(db_session, tenant.id)
    assert await adapter.get_work_order("DEMO-WO-NOTHING") is None


@pytest.mark.asyncio
async def test_update_work_order_status(db_session: AsyncSession) -> None:
    tenant, case = await seed_case(db_session)
    adapter = DemoCMMSAdapter(db_session, tenant.id)
    created = await adapter.create_work_order_draft(_request(case))
    updated = await adapter.update_work_order_status(created.external_reference, "SUBMITTED")
    assert updated.status == "SUBMITTED"


@pytest.mark.asyncio
async def test_work_orders_are_tenant_scoped(db_session: AsyncSession) -> None:
    tenant_a, case = await seed_case(db_session)
    tenant_b = await make_tenant(db_session)
    created = await DemoCMMSAdapter(db_session, tenant_a.id).create_work_order_draft(_request(case))
    fetched_from_b = await DemoCMMSAdapter(db_session, tenant_b.id).get_work_order(
        created.external_reference
    )
    assert fetched_from_b is None
