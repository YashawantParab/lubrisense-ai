from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Criticality, MachineStatus, MachineType, OperationalStatus
from app.domain.models import Bearing, LubricationSystem, Machine, Sensor
from app.repositories.machine import MachineRepository
from app.repositories.pagination import Page, PageParams
from app.repositories.production_line import ProductionLineRepository
from app.repositories.sensor import SensorRepository
from app.services.errors import ConflictError, InvalidHierarchyError, NotFoundError


@dataclass(frozen=True)
class MachineCreate:
    production_line_id: uuid.UUID
    name: str
    asset_code: str
    machine_type: MachineType
    manufacturer: str | None = None
    model: str | None = None
    serial_number_demo: str | None = None
    installation_date: date | None = None
    criticality: Criticality = Criticality.MEDIUM
    status: MachineStatus = MachineStatus.REGISTERED
    operating_profile: dict[str, Any] | None = None
    metadata_: dict[str, Any] | None = None


@dataclass(frozen=True)
class MachineFilters:
    machine_type: MachineType | None = None
    status: MachineStatus | None = None
    criticality: Criticality | None = None
    production_line_id: uuid.UUID | None = None


@dataclass(frozen=True)
class MachineHierarchy:
    """Everything the machine-detail / machine-hierarchy views need in one response:
    the machine, its bearings, its full lubrication-system chain (each with reservoirs,
    pumps, controllers, distributors, and circuits carrying their lubrication points),
    and every sensor attached anywhere in that tree."""

    machine: Machine
    bearings: list[Bearing]
    lubrication_systems: list[LubricationSystem]
    sensors: list[Sensor]


class MachineService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._lines = ProductionLineRepository(session)
        self._sensors = SensorRepository(session)

    async def create(self, tenant_id: uuid.UUID, data: MachineCreate) -> Machine:
        line = await self._lines.get(tenant_id, data.production_line_id)
        if line is None:
            raise InvalidHierarchyError(
                "PRODUCTION_LINE_NOT_FOUND_FOR_MACHINE",
                "production_line_id does not reference a production line in this tenant.",
            )
        if line.status == OperationalStatus.DECOMMISSIONED:
            raise InvalidHierarchyError(
                "PRODUCTION_LINE_DECOMMISSIONED",
                "Cannot add a machine to a decommissioned production line.",
            )
        existing = await self._machines.get_by_asset_code(tenant_id, data.asset_code)
        if existing is not None:
            raise ConflictError(
                "MACHINE_ASSET_CODE_TAKEN",
                f"A machine with asset code '{data.asset_code}' already exists for this tenant.",
            )
        machine = Machine(
            tenant_id=tenant_id,
            production_line_id=data.production_line_id,
            name=data.name,
            asset_code=data.asset_code,
            machine_type=data.machine_type,
            manufacturer=data.manufacturer,
            model=data.model,
            serial_number_demo=data.serial_number_demo,
            installation_date=data.installation_date,
            criticality=data.criticality,
            status=data.status,
            operating_profile=data.operating_profile or {},
            metadata_=data.metadata_ or {},
        )
        return await self._machines.add(machine)

    async def get(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> Machine:
        machine = await self._machines.get(tenant_id, machine_id)
        if machine is None:
            raise NotFoundError("MACHINE_NOT_FOUND", "Machine not found.")
        return machine

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        params: PageParams | None = None,
        filters: MachineFilters | None = None,
    ) -> Page[Machine]:
        clauses = []
        if filters is not None:
            if filters.machine_type is not None:
                clauses.append(Machine.machine_type == filters.machine_type)
            if filters.status is not None:
                clauses.append(Machine.status == filters.status)
            if filters.criticality is not None:
                clauses.append(Machine.criticality == filters.criticality)
            if filters.production_line_id is not None:
                clauses.append(Machine.production_line_id == filters.production_line_id)
        return await self._machines.list(tenant_id, params=params, filters=clauses)

    async def get_hierarchy(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> MachineHierarchy:
        machine = await self._machines.get_with_equipment(tenant_id, machine_id)
        if machine is None:
            raise NotFoundError("MACHINE_NOT_FOUND", "Machine not found.")

        bearing_ids = [b.id for b in machine.bearings]
        lubrication_systems = machine.lubrication_systems
        reservoir_ids = [r.id for ls in lubrication_systems for r in ls.reservoirs]
        pump_ids = [p.id for ls in lubrication_systems for p in ls.pumps]
        circuit_ids = [c.id for ls in lubrication_systems for c in ls.circuits]

        sensors = await self._sensors.list_attached_to(
            tenant_id,
            machine_ids=[machine.id],
            bearing_ids=bearing_ids,
            lubrication_system_ids=[ls.id for ls in lubrication_systems],
            reservoir_ids=reservoir_ids,
            pump_ids=pump_ids,
            circuit_ids=circuit_ids,
        )

        return MachineHierarchy(
            machine=machine,
            bearings=machine.bearings,
            lubrication_systems=lubrication_systems,
            sensors=sensors,
        )
