#!/usr/bin/env python3
"""Deterministic, idempotent demo dataset for Phase 2 (docs/ASSET_HIERARCHY.md §"Seed
data").

Seeds exactly one fictional tenant with a realistic-shaped customer/site/plant/line/
machine hierarchy, including bearings, lubrication systems (with their full reservoir/
pump/controller/distributor/circuit/lubrication-point chain), sensors, and gateways.

Every entity uses a deterministic UUID (`uuid.uuid5` over a fixed namespace and a stable
string key), so running this script twice does not create duplicate rows — see
`get_or_create()`. No telemetry, health scores, or failure events are created; this is
topology/configuration context only (LOOP.md §21, §27).

Usage:
    uv run python scripts/seed_demo_data.py
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import (
    CommercialStatus,
    CommissioningState,
    Criticality,
    LubricationSystemType,
    MachineStatus,
    MachineType,
    OperationalStatus,
    SensorQualityState,
    SensorStatus,
    SensorType,
    ServiceTier,
    TenantStatus,
)
from app.domain.models import (
    Bearing,
    Circuit,
    Controller,
    CustomerAccount,
    Distributor,
    Gateway,
    LubricationPoint,
    LubricationSystem,
    Machine,
    Plant,
    ProductionLine,
    Pump,
    Reservoir,
    Sensor,
    Site,
    Tenant,
)
from app.infrastructure.database import Database
from app.infrastructure.db_metadata import SystemMetadata

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed_demo_data")

SEED_NAMESPACE = uuid.UUID("6f3e9d5a-6c8e-4a0e-9b7f-9f6a1e2c3d4b")
SEED_VERSION = "1"
BASE_DATE = date(2024, 1, 15)

ModelT = TypeVar("ModelT")

_counts: dict[str, int] = defaultdict(int)


def det_id(*parts: str) -> uuid.UUID:
    """Deterministic UUID for a stable string key — the whole idempotency mechanism."""
    return uuid.uuid5(SEED_NAMESPACE, ":".join(parts))


async def get_or_create(
    session: AsyncSession, model_cls: type[ModelT], entity_id: uuid.UUID, **kwargs: Any
) -> ModelT:
    existing = await session.get(model_cls, entity_id)
    if existing is not None:
        return existing
    obj = model_cls(id=entity_id, **kwargs)  # type: ignore[call-arg]
    session.add(obj)
    await session.flush()
    _counts[model_cls.__name__] += 1
    return obj


MANUFACTURERS = [
    "Meridian Industrial",
    "Ironclad Bearing Works",
    "Vantage Motion Systems",
    "Solaris Controls",
    "Apex Fluid Dynamics",
    "Cascade Power Equipment",
    "Northline Machine Co.",
    "Granite Peak Industrial",
]

MACHINE_TYPE_CYCLE = [
    MachineType.CONVEYOR,
    MachineType.MOTOR,
    MachineType.FAN,
    MachineType.PUMP,
    MachineType.COMPRESSOR,
    MachineType.CRUSHER,
]

CRITICALITY_CYCLE = [Criticality.LOW, Criticality.MEDIUM, Criticality.HIGH, Criticality.CRITICAL]


def manufacturer_for(index: int) -> str:
    return MANUFACTURERS[index % len(MANUFACTURERS)]


CUSTOMERS: list[dict[str, Any]] = [
    {
        "code": "NSI",
        "name": "Northstar Industrial",
        "industry": "Metals & Mining",
        "region": "North America",
        "country": "Canada",
        "service_tier": ServiceTier.PREDICTIVE_RELIABILITY,
        "commercial_status": CommercialStatus.ACTIVE,
        "contract_start": date(2023, 6, 1),
        "contract_end": None,
        "sites": [
            {
                "code": "RIDGE",
                "name": "Ridgeline Site",
                "city": "Thunder Bay",
                "tz": "America/Toronto",
            },
            {
                "code": "HARBOR",
                "name": "Harborview Site",
                "city": "Sault Ste. Marie",
                "tz": "America/Toronto",
            },
        ],
    },
    {
        "code": "RVM",
        "name": "Riverton Manufacturing",
        "industry": "Heavy Manufacturing",
        "region": "North America",
        "country": "United States",
        "service_tier": ServiceTier.INTELLIGENT_DIAGNOSTICS,
        "commercial_status": CommercialStatus.PILOT,
        "contract_start": date(2025, 2, 1),
        "contract_end": None,
        "sites": [
            {
                "code": "MILLBROOK",
                "name": "Millbrook Site",
                "city": "Millbrook",
                "tz": "America/Chicago",
            },
            {
                "code": "EASTGATE",
                "name": "Eastgate Site",
                "city": "Eastgate",
                "tz": "America/Chicago",
            },
        ],
    },
    {
        "code": "APG",
        "name": "Atlas Processing Group",
        "industry": "Bulk Materials Processing",
        "region": "Europe",
        "country": "Germany",
        "service_tier": ServiceTier.CONNECTED_MONITORING,
        "commercial_status": CommercialStatus.PROSPECT,
        "contract_start": None,
        "contract_end": None,
        "sites": [
            {
                "code": "DORNBACH",
                "name": "Dornbach Site",
                "city": "Dornbach",
                "tz": "Europe/Berlin",
            },
        ],
    },
]

# site_code -> list of (plant_code, plant_name, plant_type)
PLANTS_BY_SITE: dict[str, list[tuple[str, str, str]]] = {
    "RIDGE": [("RIDGE-CRUSH", "Ridgeline Crushing Plant", "Crushing & Screening")],
    "HARBOR": [("HARBOR-CONV", "Harborview Conveyance Plant", "Material Handling")],
    "MILLBROOK": [
        ("MILL-ASM", "Millbrook Assembly Plant", "Assembly"),
        ("MILL-UTIL", "Millbrook Utilities Plant", "Utilities"),
    ],
    "EASTGATE": [("EAST-PROC", "Eastgate Processing Plant", "Processing")],
    "DORNBACH": [("DORN-BULK", "Dornbach Bulk Handling Plant", "Bulk Handling")],
}

# plant_code -> machine count per line (two lines per plant, L1/L2)
MACHINES_PER_LINE = {
    "RIDGE-CRUSH": [3, 2],
    "HARBOR-CONV": [2, 2],
    "MILL-ASM": [2, 2],
    "MILL-UTIL": [2, 1],
    "EAST-PROC": [2, 2],
    "DORN-BULK": [2, 2],
}


async def seed(session: AsyncSession) -> None:
    tenant = await get_or_create(
        session,
        Tenant,
        det_id("tenant", "lubrisense-demo"),
        name="LubriSense Demo Tenant",
        slug="lubrisense-demo",
        status=TenantStatus.ACTIVE,
    )
    tenant_id = tenant.id

    machine_index = 0

    for customer_data in CUSTOMERS:
        customer = await get_or_create(
            session,
            CustomerAccount,
            det_id("customer", customer_data["code"]),
            tenant_id=tenant_id,
            name=customer_data["name"],
            code=customer_data["code"],
            industry=customer_data["industry"],
            region=customer_data["region"],
            country=customer_data["country"],
            service_tier=customer_data["service_tier"],
            commercial_status=customer_data["commercial_status"],
            contract_start=customer_data["contract_start"],
            contract_end=customer_data["contract_end"],
            metadata_={"demo": True},
        )

        for site_data in customer_data["sites"]:
            site = await get_or_create(
                session,
                Site,
                det_id("site", site_data["code"]),
                tenant_id=tenant_id,
                customer_account_id=customer.id,
                name=site_data["name"],
                code=site_data["code"],
                country=customer_data["country"],
                city=site_data["city"],
                timezone=site_data["tz"],
                status=OperationalStatus.ACTIVE,
                metadata_={"demo": True},
            )

            for plant_code, plant_name, plant_type in PLANTS_BY_SITE[site_data["code"]]:
                plant = await get_or_create(
                    session,
                    Plant,
                    det_id("plant", plant_code),
                    tenant_id=tenant_id,
                    site_id=site.id,
                    name=plant_name,
                    code=plant_code,
                    plant_type=plant_type,
                    status=OperationalStatus.ACTIVE,
                    metadata_={"demo": True},
                )

                for line_offset, machine_count in enumerate(MACHINES_PER_LINE[plant_code]):
                    line_code = f"L{line_offset + 1}"
                    line = await get_or_create(
                        session,
                        ProductionLine,
                        det_id("line", plant_code, line_code),
                        tenant_id=tenant_id,
                        plant_id=plant.id,
                        name=f"{plant_name.split(' Plant')[0]} Line {chr(65 + line_offset)}",
                        code=line_code,
                        description=f"Production line {line_offset + 1} of {plant_name}.",
                        status=OperationalStatus.ACTIVE,
                        criticality=CRITICALITY_CYCLE[machine_index % len(CRITICALITY_CYCLE)],
                        metadata_={"demo": True},
                    )

                    for _ in range(machine_count):
                        await seed_machine(session, tenant_id, line, machine_index)
                        machine_index += 1

    await seed_gateways(session, tenant_id)

    await get_or_create_system_metadata(session)


async def seed_machine(
    session: AsyncSession, tenant_id: uuid.UUID, line: ProductionLine, index: int
) -> None:
    machine_type = MACHINE_TYPE_CYCLE[index % len(MACHINE_TYPE_CYCLE)]
    asset_code = f"{line.code}-{line.plant_id.hex[:4].upper()}-M{index:03d}"
    equipment_tier = index % 4  # 0,1 = full chain; 2 = bearings only; 3 = bare

    machine = await get_or_create(
        session,
        Machine,
        det_id("machine", str(index)),
        tenant_id=tenant_id,
        production_line_id=line.id,
        name=f"{machine_type.value.title()} {index:03d}",
        asset_code=asset_code,
        machine_type=machine_type,
        manufacturer=manufacturer_for(index),
        model=f"{machine_type.value[:2].upper()}-{100 + index}",
        serial_number_demo=f"DEMO-SN-{index:05d}",
        installation_date=BASE_DATE + timedelta(days=index * 11),
        criticality=CRITICALITY_CYCLE[(index + 1) % len(CRITICALITY_CYCLE)],
        operating_profile={"duty_cycle": "continuous" if index % 2 == 0 else "intermittent"},
        status=MachineStatus.REGISTERED if equipment_tier == 3 else MachineStatus.MONITORED,
        metadata_={"demo": True},
    )

    if equipment_tier == 3:
        return  # bare machine: topology only, nothing downstream yet

    bearings = []
    for position in ("DRIVE_END", "NON_DRIVE_END"):
        bearing = await get_or_create(
            session,
            Bearing,
            det_id("bearing", str(index), position),
            tenant_id=tenant_id,
            machine_id=machine.id,
            name=f"{machine.name} — {position.replace('_', ' ').title()} Bearing",
            position=position,
            bearing_type="Deep Groove Ball" if index % 2 == 0 else "Spherical Roller",
            manufacturer=manufacturer_for(index + 3),
            model=f"BRG-{200 + index}",
            criticality=machine.criticality,
            installation_date=machine.installation_date,
            status=OperationalStatus.ACTIVE,
            metadata_={"demo": True},
        )
        bearings.append(bearing)

    if equipment_tier == 2:
        for bearing in bearings:
            await get_or_create(
                session,
                Sensor,
                det_id("sensor", "vibration", str(bearing.id)),
                tenant_id=tenant_id,
                sensor_code=f"VIB-{bearing.id.hex[:8]}",
                name=f"{bearing.name} Vibration Sensor",
                sensor_type=SensorType.VIBRATION_RMS,
                unit="mm/s",
                installation_date=machine.installation_date,
                calibration_date=machine.installation_date,
                status=SensorStatus.ACTIVE,
                quality_state=SensorQualityState.UNKNOWN,
                bearing_id=bearing.id,
                metadata_={"demo": True},
            )
        return  # bearings-only: no lubrication system yet

    await seed_lubrication_system(session, tenant_id, machine, bearings, index)


async def seed_lubrication_system(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    machine: Machine,
    bearings: list[Bearing],
    index: int,
) -> None:
    system_type = list(LubricationSystemType)[index % len(list(LubricationSystemType))]
    system = await get_or_create(
        session,
        LubricationSystem,
        det_id("lubsys", str(index)),
        tenant_id=tenant_id,
        machine_id=machine.id,
        name=f"{machine.name} Lubrication System",
        system_type=system_type,
        status=OperationalStatus.ACTIVE,
        commissioning_state=CommissioningState.COMMISSIONED,
        configuration_version="v1",
        metadata_={"demo": True},
    )

    reservoir = await get_or_create(
        session,
        Reservoir,
        det_id("reservoir", str(index)),
        tenant_id=tenant_id,
        lubrication_system_id=system.id,
        name=f"{machine.name} Reservoir",
        capacity_demo=10 + (index % 5) * 5,
        capacity_unit="L",
        lubricant_type_demo="NLGI 2 grease (demo)" if index % 2 == 0 else "ISO VG 220 oil (demo)",
        status=OperationalStatus.ACTIVE,
        metadata_={"demo": True},
    )
    pump = await get_or_create(
        session,
        Pump,
        det_id("pump", str(index)),
        tenant_id=tenant_id,
        lubrication_system_id=system.id,
        name=f"{machine.name} Pump",
        pump_type="Progressive" if index % 2 == 0 else "Gear",
        manufacturer=manufacturer_for(index + 1),
        model=f"PMP-{300 + index}",
        status=OperationalStatus.ACTIVE,
        firmware_version_demo="1.0.0-demo",
        metadata_={"demo": True},
    )
    controller = await get_or_create(
        session,
        Controller,
        det_id("controller", str(index)),
        tenant_id=tenant_id,
        lubrication_system_id=system.id,
        name=f"{machine.name} Controller",
        controller_type="Timer-based" if index % 2 == 0 else "Cycle-based",
        manufacturer=manufacturer_for(index + 2),
        model=f"CTRL-{400 + index}",
        firmware_version="2.1.0-demo",
        configuration_version="v1",
        status=OperationalStatus.ACTIVE,
        metadata_={"demo": True},
    )
    distributor = await get_or_create(
        session,
        Distributor,
        det_id("distributor", str(index)),
        tenant_id=tenant_id,
        lubrication_system_id=system.id,
        name=f"{machine.name} Distributor",
        type="Modular piston",
        position="primary",
        status=OperationalStatus.ACTIVE,
        metadata_={"demo": True},
    )

    system.reservoir_id = reservoir.id
    system.pump_id = pump.id
    system.controller_id = controller.id
    await session.flush()

    for circuit_index, bearing in enumerate(bearings):
        circuit = await get_or_create(
            session,
            Circuit,
            det_id("circuit", str(index), str(circuit_index)),
            tenant_id=tenant_id,
            lubrication_system_id=system.id,
            distributor_id=distributor.id,
            name=f"{machine.name} Circuit {circuit_index + 1}",
            code=f"C{circuit_index + 1}",
            status=OperationalStatus.ACTIVE,
            metadata_={"demo": True},
        )
        await get_or_create(
            session,
            LubricationPoint,
            det_id("lubpoint", str(index), str(circuit_index)),
            tenant_id=tenant_id,
            circuit_id=circuit.id,
            bearing_id=bearing.id,
            name=f"{bearing.name} Lubrication Point",
            code=f"LP{circuit_index + 1}",
            status=OperationalStatus.ACTIVE,
            metadata_={"demo": True},
        )
        if circuit_index == 0:
            await get_or_create(
                session,
                Sensor,
                det_id("sensor", "pressure", str(index)),
                tenant_id=tenant_id,
                sensor_code=f"PRS-{circuit.id.hex[:8]}",
                name=f"{circuit.name} Pressure Sensor",
                sensor_type=SensorType.PRESSURE,
                unit="bar",
                installation_date=machine.installation_date,
                status=SensorStatus.ACTIVE,
                quality_state=SensorQualityState.UNKNOWN,
                circuit_id=circuit.id,
                metadata_={"demo": True},
            )

    await get_or_create(
        session,
        Sensor,
        det_id("sensor", "reservoir_level", str(index)),
        tenant_id=tenant_id,
        sensor_code=f"LVL-{reservoir.id.hex[:8]}",
        name=f"{reservoir.name} Level Sensor",
        sensor_type=SensorType.RESERVOIR_LEVEL,
        unit="%",
        installation_date=machine.installation_date,
        status=SensorStatus.ACTIVE,
        quality_state=SensorQualityState.UNKNOWN,
        reservoir_id=reservoir.id,
        metadata_={"demo": True},
    )
    await get_or_create(
        session,
        Sensor,
        det_id("sensor", "pump_current", str(index)),
        tenant_id=tenant_id,
        sensor_code=f"CUR-{pump.id.hex[:8]}",
        name=f"{pump.name} Current Sensor",
        sensor_type=SensorType.PUMP_CURRENT,
        unit="A",
        installation_date=machine.installation_date,
        status=SensorStatus.ACTIVE,
        quality_state=SensorQualityState.UNKNOWN,
        pump_id=pump.id,
        metadata_={"demo": True},
    )
    for bearing in bearings:
        await get_or_create(
            session,
            Sensor,
            det_id("sensor", "bearing_temp", str(bearing.id)),
            tenant_id=tenant_id,
            sensor_code=f"TMP-{bearing.id.hex[:8]}",
            name=f"{bearing.name} Temperature Sensor",
            sensor_type=SensorType.BEARING_TEMPERATURE,
            unit="°C",
            installation_date=machine.installation_date,
            status=SensorStatus.ACTIVE,
            quality_state=SensorQualityState.UNKNOWN,
            bearing_id=bearing.id,
            metadata_={"demo": True},
        )
        await get_or_create(
            session,
            Sensor,
            det_id("sensor", "vibration", str(bearing.id)),
            tenant_id=tenant_id,
            sensor_code=f"VIB-{bearing.id.hex[:8]}",
            name=f"{bearing.name} Vibration Sensor",
            sensor_type=SensorType.VIBRATION_RMS,
            unit="mm/s",
            installation_date=machine.installation_date,
            status=SensorStatus.ACTIVE,
            quality_state=SensorQualityState.UNKNOWN,
            bearing_id=bearing.id,
            metadata_={"demo": True},
        )
    await get_or_create(
        session,
        Sensor,
        det_id("sensor", "rpm", str(index)),
        tenant_id=tenant_id,
        sensor_code=f"RPM-{machine.id.hex[:8]}",
        name=f"{machine.name} RPM Sensor",
        sensor_type=SensorType.RPM,
        unit="rpm",
        installation_date=machine.installation_date,
        status=SensorStatus.ACTIVE,
        quality_state=SensorQualityState.UNKNOWN,
        machine_id=machine.id,
        metadata_={"demo": True},
    )


async def seed_gateways(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    site_gateways = ["RIDGE", "HARBOR", "MILLBROOK"]
    plant_gateways = ["RIDGE-CRUSH", "MILL-ASM", "DORN-BULK"]

    for site_code in site_gateways:
        site = await session.get(Site, det_id("site", site_code))
        assert site is not None
        await get_or_create(
            session,
            Gateway,
            det_id("gateway", "site", site_code),
            tenant_id=tenant_id,
            site_id=site.id,
            name=f"{site.name} Gateway",
            gateway_code=f"GW-{site_code}",
            manufacturer_demo="Solaris Controls",
            model_demo="EdgeLink-100 (demo)",
            firmware_version="0.9.0-demo",
            status=OperationalStatus.ACTIVE,
            last_seen=None,
            metadata_={"demo": True},
        )

    for plant_code in plant_gateways:
        plant = await session.get(Plant, det_id("plant", plant_code))
        assert plant is not None
        await get_or_create(
            session,
            Gateway,
            det_id("gateway", "plant", plant_code),
            tenant_id=tenant_id,
            plant_id=plant.id,
            name=f"{plant.name} Gateway",
            gateway_code=f"GW-{plant_code}",
            manufacturer_demo="Solaris Controls",
            model_demo="EdgeLink-100 (demo)",
            firmware_version="0.9.0-demo",
            status=OperationalStatus.ACTIVE,
            last_seen=None,
            metadata_={"demo": True},
        )


async def get_or_create_system_metadata(session: AsyncSession) -> None:
    existing = await session.get(SystemMetadata, "demo_seed_version")
    if existing is None:
        session.add(SystemMetadata(key="demo_seed_version", value=SEED_VERSION))
    elif existing.value != SEED_VERSION:
        existing.value = SEED_VERSION
    await session.flush()


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    try:
        async with database.session() as session:
            await seed(session)
            await session.commit()
    finally:
        await database.dispose()

    if _counts:
        logger.info("Created:")
        for name, count in sorted(_counts.items()):
            logger.info("  %-20s %d", name, count)
    else:
        logger.info("Nothing to create — demo dataset already seeded (idempotent no-op).")


if __name__ == "__main__":
    asyncio.run(main())
