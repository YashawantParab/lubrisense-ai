"""`DeviceConfigurationService` — real-Postgres integration tests (Phase 31 brief §31.3-
§31.6): snapshot supersession, append-only change history, compatibility
classification, and the significant-change/baseline-review-required boundary."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditActor
from app.device_management.compatibility import classify_compatibility
from app.device_management.service import DeviceConfigurationService
from app.domain.enums import AuditActorType, CompatibilityStatus, DeviceType
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
)


def _actor() -> AuditActor:
    return AuditActor(actor_id="test-admin", actor_type=AuditActorType.HUMAN, role="ADMIN")


@pytest.mark.parametrize(
    ("firmware_version", "expected"),
    [
        (None, CompatibilityStatus.UNKNOWN),
        ("garbage", CompatibilityStatus.UNKNOWN),
        ("0.9.0", CompatibilityStatus.INCOMPATIBLE),
        ("1.4.0", CompatibilityStatus.SUPPORTED_WITH_LIMITATIONS),
        ("2.1.0", CompatibilityStatus.SUPPORTED),
        ("3.0.0", CompatibilityStatus.SUPPORTED),
    ],
)
def test_classify_compatibility(
    firmware_version: str | None, expected: CompatibilityStatus
) -> None:
    assert classify_compatibility(firmware_version) == expected


@pytest.mark.asyncio
async def test_capture_snapshot_supersedes_prior_current(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)

    device_id = uuid.uuid4()
    service = DeviceConfigurationService(db_session)

    first = await service.capture_snapshot(
        tenant.id,
        machine_id=machine.id,
        device_type=DeviceType.SENSOR,
        device_id=device_id,
        config={"unit": "bar"},
        firmware_version="1.0.0",
        actor=_actor(),
        reason="initial",
        source="test",
    )
    assert first.is_current is True

    second = await service.capture_snapshot(
        tenant.id,
        machine_id=machine.id,
        device_type=DeviceType.SENSOR,
        device_id=device_id,
        config={"unit": "psi"},
        firmware_version="2.0.0",
        actor=_actor(),
        reason="unit changed",
        source="test",
    )
    await db_session.refresh(first)

    assert first.is_current is False
    assert second.is_current is True

    current = await service.get_machine_devices(tenant.id, machine.id)
    assert len(current) == 1
    assert current[0].id == second.id


@pytest.mark.asyncio
async def test_initial_snapshot_never_requires_baseline_review(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)

    service = DeviceConfigurationService(db_session)
    await service.capture_snapshot(
        tenant.id,
        machine_id=machine.id,
        device_type=DeviceType.GATEWAY,
        device_id=uuid.uuid4(),
        config={"sampling_interval_seconds": 30},
        firmware_version="2.0.0",
        actor=_actor(),
        reason="commissioned",
        source="test",
    )

    changes = await service.list_changes(tenant.id, machine.id)
    assert len(changes) == 1
    assert changes[0].baseline_review_required is False
    assert changes[0].previous_snapshot_id is None


@pytest.mark.asyncio
async def test_significant_change_flags_baseline_review_required(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    device_id = uuid.uuid4()

    service = DeviceConfigurationService(db_session)
    await service.capture_snapshot(
        tenant.id,
        machine_id=machine.id,
        device_type=DeviceType.GATEWAY,
        device_id=device_id,
        config={"sampling_interval_seconds": 30},
        firmware_version="2.0.0",
        actor=_actor(),
        reason="commissioned",
        source="test",
    )
    await service.capture_snapshot(
        tenant.id,
        machine_id=machine.id,
        device_type=DeviceType.GATEWAY,
        device_id=device_id,
        config={"sampling_interval_seconds": 5},  # significant field changed
        firmware_version="2.0.0",
        actor=_actor(),
        reason="sampling interval tuned",
        source="test",
    )

    changes = await service.list_changes(tenant.id, machine.id)
    assert len(changes) == 2
    latest = changes[0]  # ordered most-recent-first
    assert latest.baseline_review_required is True
    assert latest.previous_snapshot_id is not None


@pytest.mark.asyncio
async def test_insignificant_change_does_not_flag_baseline_review(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    device_id = uuid.uuid4()

    service = DeviceConfigurationService(db_session)
    await service.capture_snapshot(
        tenant.id,
        machine_id=machine.id,
        device_type=DeviceType.GATEWAY,
        device_id=device_id,
        config={"sampling_interval_seconds": 30, "label": "Gateway A"},
        firmware_version="2.0.0",
        actor=_actor(),
        reason="commissioned",
        source="test",
    )
    await service.capture_snapshot(
        tenant.id,
        machine_id=machine.id,
        device_type=DeviceType.GATEWAY,
        device_id=device_id,
        config={"sampling_interval_seconds": 30, "label": "Gateway A (renamed)"},
        firmware_version="2.0.0",
        actor=_actor(),
        reason="cosmetic label change",
        source="test",
    )

    changes = await service.list_changes(tenant.id, machine.id)
    assert changes[0].baseline_review_required is False
