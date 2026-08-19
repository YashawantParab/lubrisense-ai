"""`CommissioningService` — the guided demo onboarding workflow (Phase 30 brief §30.2).

Step order: `start_session` (creates the `Machine` + session together) → `add_sensor`
(repeatable) → `assign_gateway` (optional) → `validate` → `complete`. Each step is a
separate, idempotent-enough API call so a frontend wizard can drive it one screen at a
time; nothing here waits for or requires a real physical device to respond.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditActor, AuditService
from app.commissioning.policy import compute_capability_level, is_unit_expected
from app.commissioning.repository import CommissioningSessionRepository
from app.device_management.service import DeviceConfigurationService
from app.domain.enums import (
    CommissioningStatus,
    DeviceType,
    MachineStatus,
    SensorType,
)
from app.domain.models import CommissioningSession, Machine, Sensor
from app.repositories.gateway import GatewayRepository
from app.repositories.machine import MachineRepository
from app.repositories.sensor import SensorRepository
from app.services.errors import ConflictError, NotFoundError


class InvalidCommissioningTransitionError(Exception):
    pass


class CommissioningService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sessions = CommissioningSessionRepository(session)
        self._machines = MachineRepository(session)
        self._sensors = SensorRepository(session)
        self._gateways = GatewayRepository(session)
        self._devices = DeviceConfigurationService(session)

    async def start_session(
        self,
        tenant_id: uuid.UUID,
        *,
        production_line_id: uuid.UUID,
        name: str,
        asset_code: str,
        machine_type: str,
        actor: AuditActor,
    ) -> CommissioningSession:
        existing = await self._machines.get_by_asset_code(tenant_id, asset_code)
        if existing is not None:
            raise ConflictError(
                "ASSET_CODE_TAKEN", f"A machine with asset code '{asset_code}' already exists."
            )

        machine = Machine(
            tenant_id=tenant_id,
            production_line_id=production_line_id,
            name=name,
            asset_code=asset_code,
            machine_type=machine_type,
            status=MachineStatus.COMMISSIONING,
        )
        machine = await self._machines.add(machine)

        session = CommissioningSession(
            tenant_id=tenant_id,
            machine_id=machine.id,
            status=CommissioningStatus.CONFIGURING,
            steps_completed=["machine_registered"],
        )
        return await self._sessions.add(session)

    async def get(self, tenant_id: uuid.UUID, session_id: uuid.UUID) -> CommissioningSession:
        session = await self._sessions.get(tenant_id, session_id)
        if session is None:
            raise NotFoundError(
                "COMMISSIONING_SESSION_NOT_FOUND", "Commissioning session not found."
            )
        return session

    async def list_sessions(self, tenant_id: uuid.UUID) -> list[CommissioningSession]:
        page = await self._sessions.list(tenant_id)
        return list(page.items)

    async def add_sensor(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        *,
        sensor_type: SensorType,
        sensor_code: str,
        name: str,
        unit: str | None,
        actor: AuditActor,
    ) -> Sensor:
        session = await self.get(tenant_id, session_id)
        if session.status not in (CommissioningStatus.CONFIGURING, CommissioningStatus.FAILED):
            raise InvalidCommissioningTransitionError(
                f"Cannot add a sensor while session is {session.status.value}."
            )

        sensor = Sensor(
            tenant_id=tenant_id,
            sensor_code=sensor_code,
            name=name,
            sensor_type=sensor_type,
            unit=unit,
            machine_id=session.machine_id,
        )
        sensor = await self._sensors.add(sensor)

        await self._devices.capture_snapshot(
            tenant_id,
            machine_id=session.machine_id,
            device_type=DeviceType.SENSOR,
            device_id=sensor.id,
            config={"sensor_type": sensor_type.value, "unit": unit, "sensor_code": sensor_code},
            firmware_version=None,
            actor=actor,
            reason="Sensor registered during commissioning.",
            source="commissioning.add_sensor",
        )

        session.steps_completed = [*session.steps_completed, f"sensor_mapped:{sensor.id}"]
        session.status = CommissioningStatus.CONFIGURING
        return sensor

    async def assign_gateway(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        *,
        gateway_id: uuid.UUID,
        actor: AuditActor,
    ) -> CommissioningSession:
        session = await self.get(tenant_id, session_id)
        gateway = await self._gateways.get(tenant_id, gateway_id)
        if gateway is None:
            raise NotFoundError("GATEWAY_NOT_FOUND", "Gateway not found.")

        session.gateway_id = gateway.id
        session.steps_completed = [*session.steps_completed, f"gateway_assigned:{gateway.id}"]

        await self._devices.capture_snapshot(
            tenant_id,
            machine_id=session.machine_id,
            device_type=DeviceType.GATEWAY,
            device_id=gateway.id,
            config={"gateway_code": gateway.gateway_code},
            firmware_version=gateway.firmware_version,
            actor=actor,
            reason="Gateway assigned during commissioning.",
            source="commissioning.assign_gateway",
        )
        await self._session.flush()
        await self._session.refresh(session)
        return session

    async def validate(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> CommissioningSession:
        session = await self.get(tenant_id, session_id)
        session.status = CommissioningStatus.VALIDATING

        sensors = await self._sensors.list_attached_to(tenant_id, machine_ids=[session.machine_id])
        sensor_types = {s.sensor_type for s in sensors}
        capability = compute_capability_level(sensor_types)

        issues: list[dict[str, Any]] = []
        blocking = False

        if not sensors:
            issues.append(
                {
                    "code": "NO_INSTRUMENTATION",
                    "message": "No sensors have been mapped to this machine yet.",
                    "blocking": True,
                }
            )
            blocking = True

        for sensor in sensors:
            if not is_unit_expected(sensor.sensor_type, sensor.unit):
                issues.append(
                    {
                        "code": "UNEXPECTED_UNIT",
                        "message": (
                            f"Sensor {sensor.sensor_code} ({sensor.sensor_type.value}) has an "
                            f"unexpected unit '{sensor.unit}'."
                        ),
                        "blocking": False,
                    }
                )

        if session.gateway_id is not None:
            gateway = await self._gateways.get(tenant_id, session.gateway_id)
            if gateway is not None and gateway.status.value != "ACTIVE":
                issues.append(
                    {
                        "code": "GATEWAY_NOT_ACTIVE",
                        "message": f"Assigned gateway is {gateway.status.value}, not ACTIVE.",
                        "blocking": False,
                    }
                )
        else:
            issues.append(
                {
                    "code": "NO_GATEWAY_ASSIGNED",
                    "message": (
                        "No gateway has been assigned — telemetry cannot reach the platform."
                    ),
                    "blocking": False,
                }
            )

        issues.append(
            {
                "code": "NO_TELEMETRY_YET",
                "message": (
                    "No telemetry has been received yet — expected for a freshly commissioned "
                    "demo asset until the edge/simulator pipeline runs."
                ),
                "blocking": False,
            }
        )

        session.capability_level = capability
        session.validation_issues = issues
        session.steps_completed = [*session.steps_completed, "validated"]
        session.status = CommissioningStatus.FAILED if blocking else CommissioningStatus.READY
        return session

    async def complete(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, *, actor: AuditActor
    ) -> CommissioningSession:
        session = await self.get(tenant_id, session_id)
        if session.status != CommissioningStatus.READY:
            raise InvalidCommissioningTransitionError(
                f"Cannot complete a session in status {session.status.value}; must be READY."
            )

        machine = await self._machines.get(tenant_id, session.machine_id)
        if machine is not None:
            machine.status = MachineStatus.MONITORED

        session.status = CommissioningStatus.COMPLETED
        session.completed_at = datetime.now(UTC)
        session.steps_completed = [*session.steps_completed, "completed"]

        await AuditService(self._session).record(
            tenant_id,
            actor=actor,
            action="COMMISSIONING_COMPLETED",
            entity_type="machine",
            entity_id=session.machine_id,
            source="commissioning.complete",
            after_summary=f"Capability level: {session.capability_level.value}.",
        )
        await self._session.flush()
        await self._session.refresh(session)
        return session
