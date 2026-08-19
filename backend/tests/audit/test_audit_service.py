"""`AuditService`/`AuditEventRepository` unit tests (Phase 25 brief §25.1/§25.4/§25.5):
recording, actor-type distinction, and append-only search/filter behavior."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditEventRepository
from app.audit.service import AuditActor, AuditService
from app.domain.enums import AuditActorType
from app.repositories.pagination import PageParams
from tests.factories import make_tenant


@pytest.mark.asyncio
async def test_record_persists_all_fields(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    entity_id = uuid.uuid4()

    event = await AuditService(db_session).record(
        tenant.id,
        actor=AuditActor(actor_id="demo-admin", actor_type=AuditActorType.HUMAN, role="ADMIN"),
        action="TEST_ACTION",
        entity_type="test_entity",
        entity_id=entity_id,
        source="test",
        before_summary="before",
        after_summary="after",
        reason="because",
        correlation_id="corr-123",
    )

    assert event.actor_id == "demo-admin"
    assert event.actor_type == AuditActorType.HUMAN
    assert event.role == "ADMIN"
    assert event.action == "TEST_ACTION"
    assert event.entity_type == "test_entity"
    assert event.entity_id == str(entity_id)
    assert event.correlation_id == "corr-123"
    assert event.before_summary == "before"
    assert event.after_summary == "after"
    assert event.reason == "because"
    assert event.source == "test"


@pytest.mark.asyncio
async def test_record_falls_back_to_context_correlation_id_when_none_given(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    event = await AuditService(db_session).record(
        tenant.id,
        actor=AuditActor.system("worker"),
        action="X",
        entity_type="y",
        entity_id="z",
        source="test",
    )
    assert event.correlation_id  # never empty/None


@pytest.mark.asyncio
async def test_search_filters_by_actor_and_entity(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    service = AuditService(db_session)
    entity_id = uuid.uuid4()

    await service.record(
        tenant.id,
        actor=AuditActor.system("system-actor"),
        action="A",
        entity_type="incident",
        entity_id=entity_id,
        source="test",
    )
    await service.record(
        tenant.id,
        actor=AuditActor.agent("guarded-agent"),
        action="B",
        entity_type="agent_session",
        entity_id=uuid.uuid4(),
        source="test",
    )

    repo = AuditEventRepository(db_session)
    page = await repo.search(tenant.id, entity_type="incident", params=PageParams())
    assert page.total == 1
    assert page.items[0].actor_type == AuditActorType.SYSTEM

    page_by_action = await repo.search(tenant.id, action="B", params=PageParams())
    assert page_by_action.total == 1
    assert page_by_action.items[0].actor_type == AuditActorType.AGENT


@pytest.mark.asyncio
async def test_search_is_tenant_scoped(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    service = AuditService(db_session)
    await service.record(
        tenant_a.id,
        actor=AuditActor.system("s"),
        action="TENANT_A_ACTION",
        entity_type="e",
        entity_id="1",
        source="test",
    )

    repo = AuditEventRepository(db_session)
    page = await repo.search(tenant_b.id, params=PageParams())
    assert page.total == 0
