"""`DeviceConfigurationService` — captures configuration/firmware snapshots and their
append-only change history (Phase 31 brief §31.3/§31.4). Visibility/governance only: no
method here ever sends a command to a device (§31.7 — no OTA, no remote configuration
push).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditActor, AuditService
from app.device_management.compatibility import classify_compatibility
from app.device_management.repository import (
    ConfigurationChangeRepository,
    ConfigurationSnapshotRepository,
)
from app.domain.enums import DeviceType
from app.domain.models import ConfigurationChange, ConfigurationSnapshot

#: config keys whose change is considered significant enough to flag a baseline for
#: human review (Phase 31 brief §31.6) — a deliberately small, explicit list rather than
#: "any config difference," since most config fields (e.g. a device label) have no
#: bearing on how existing baselines should be interpreted.
_BASELINE_SENSITIVE_KEYS = frozenset({"sampling_interval_seconds", "unit", "calibration_offset"})


def _is_significant_change(
    previous: ConfigurationSnapshot | None, new_config: dict[str, Any], new_firmware: str | None
) -> bool:
    if previous is None:
        return False  # an initial snapshot has no prior baseline to invalidate
    if previous.firmware_version != new_firmware:
        return True
    return any(previous.config.get(key) != new_config.get(key) for key in _BASELINE_SENSITIVE_KEYS)


class DeviceConfigurationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._snapshots = ConfigurationSnapshotRepository(session)
        self._changes = ConfigurationChangeRepository(session)

    async def capture_snapshot(
        self,
        tenant_id: uuid.UUID,
        *,
        machine_id: uuid.UUID,
        device_type: DeviceType,
        device_id: uuid.UUID,
        config: dict[str, Any],
        firmware_version: str | None,
        actor: AuditActor,
        reason: str | None,
        source: str,
    ) -> ConfigurationSnapshot:
        previous = await self._snapshots.get_current(tenant_id, device_type, device_id)
        baseline_review_required = _is_significant_change(previous, config, firmware_version)

        if previous is not None:
            previous.is_current = False
            await self._session.flush()

        snapshot = ConfigurationSnapshot(
            tenant_id=tenant_id,
            machine_id=machine_id,
            device_type=device_type,
            device_id=device_id,
            firmware_version=firmware_version,
            config=config,
            compatibility_status=classify_compatibility(firmware_version),
            is_current=True,
            captured_at=datetime.now(UTC),
        )
        snapshot = await self._snapshots.add(snapshot)

        change = ConfigurationChange(
            tenant_id=tenant_id,
            machine_id=machine_id,
            device_type=device_type,
            device_id=device_id,
            previous_snapshot_id=previous.id if previous else None,
            new_snapshot_id=snapshot.id,
            changed_by=actor.actor_id,
            reason=reason,
            source=source,
            baseline_review_required=baseline_review_required,
            occurred_at=datetime.now(UTC),
        )
        await self._changes.add(change)

        await AuditService(self._session).record(
            tenant_id,
            actor=actor,
            action="DEVICE_CONFIGURATION_CHANGED",
            entity_type="configuration_snapshot",
            entity_id=snapshot.id,
            source=source,
            before_summary=(
                f"{previous.device_type.value} firmware {previous.firmware_version}"
                if previous
                else None
            ),
            after_summary=f"{snapshot.device_type.value} firmware {snapshot.firmware_version}",
            reason=reason,
        )

        return snapshot

    async def get_machine_devices(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[ConfigurationSnapshot]:
        return await self._snapshots.list_current_for_machine(tenant_id, machine_id)

    async def list_changes(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[ConfigurationChange]:
        return await self._changes.list_for_machine(tenant_id, machine_id)
