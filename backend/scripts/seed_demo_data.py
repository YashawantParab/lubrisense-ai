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
from typing import Any, NamedTuple, TypeVar

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
    """Upsert by deterministic id: creates the row if absent, otherwise patches any of
    the given fields that have drifted from what this script currently defines (e.g. a
    display name revised in a later edit of this file) — the same merge-patch-on-reseed
    idiom `mark_sensor_quality` uses elsewhere, applied here to the base hierarchy so a
    naming/copy change actually reaches an already-seeded database on the next run,
    without ever touching `id` or any column this call doesn't pass."""
    existing = await session.get(model_cls, entity_id)
    if existing is not None:
        changed = False
        for key, value in kwargs.items():
            if getattr(existing, key) != value:
                setattr(existing, key, value)
                changed = True
        if changed:
            await session.flush()
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


# Industrial-asset-realism pass: the ten curated, scenario-scripted machines (indices
# fixed by `seed_hosted_demo.py` / the individual `scripts/seed_*.py` scenario scripts,
# which resolve by `asset_code` — see those scripts' own `ASSET_CODE`/`FLAGSHIP_ASSET_CODE`
# constants, none of which change here) get a real centralized-lubrication equipment
# identity instead of a generic "{MachineType} {index:03d}" label. Every other machine in
# the generated fleet keeps the generic formula unchanged.
#
#   - `display_name` is the full `Machine.name` shown everywhere a machine header appears
#     (Overview/Fleet/Machine Detail/Incidents/.../Technical Provenance) — API-driven, so
#     this one field is the only thing that needs to change for every page to agree.
#   - `short_label` is what cascades into this machine's own bearing/reservoir/pump/
#     controller/distributor/circuit/sensor names (`seed_machine`/`seed_lubrication_
#     system` below) — kept short specifically so e.g. a sensor name doesn't become
#     "Ore Transfer Conveyor CV-101 – Head Pulley Bearings Reservoir Level Sensor".
#   - `equipment_class` and `area` (industrial-context-consistency pass) are seeded into
#     `Machine.metadata_`, not a mapped column — read back via `HierarchyMachine`'s
#     `_extract_metadata_fields` validator (`app/api/schemas/hierarchy.py`) and
#     `MachineResponse.metadata_` directly. `equipment_class` is the product-presentation
#     equipment type primary UI should lead with (`frontend/src/lib/equipment.ts`'s
#     `equipmentTypeFor`); `area` is a synthetic process-area label used in place of the
#     literal Plant/Line name in primary UI specifically because two curated machines
#     (indices 0 and 1) share a physical `ProductionLine` whose real name — "Ridgeline
#     Crushing Plant" — reads as a non-sequitur next to a kiln drive. Neither field
#     changes `production_line_id`/`asset_code`/`id`: the real structural Plant/Line
#     assignment is untouched and still renders correctly in the Asset Hierarchy
#     engineering tree.
#
# machine_type (fixed by `MACHINE_TYPE_CYCLE[index % 6]`, never changed here) is the
# platform's only equipment-category *column* — six fixed values (CLAUDE.md's machine
# hierarchy) kept for backend/simulator/historical-test compatibility. Real industrial
# catalogs are far more specific than six categories, so a handful of these (a kiln/mill/
# feeder run by its drive MOTOR, a rolling mill's lubrication skid classed as its
# COMPRESSOR-family machine) are a coarse-category fit rather than a literal one — exactly
# why `equipment_class` exists as the customer-facing override. Scenario (telemetry/
# incident/condition story) is unchanged for every one of these; only identity/copy
# changed.
class _CuratedMachine(NamedTuple):
    display_name: str
    short_label: str
    equipment_class: str
    area: str


CURATED_MACHINE_NAMES: dict[int, _CuratedMachine] = {
    0: _CuratedMachine(  # L1-7B43-M000, CONVEYOR — flagship: resolved lubrication restriction
        "Ore Transfer Conveyor CV-101 – Head Pulley Bearings",
        "Ore Transfer Conveyor CV-101",
        "Ore Transfer Conveyor",
        "Bulk Material Handling",
    ),
    1: _CuratedMachine(  # L1-7B43-M001, MOTOR — healthy, stable, high-confidence
        "Rotary Kiln Drive KILN-01 – Support Roller Station 2",
        "Rotary Kiln Drive KILN-01",
        "Rotary Kiln Drive",
        "Pyroprocessing",
    ),
    4: _CuratedMachine(  # L2-7B43-M004, COMPRESSOR — lubrication pump performance degradation
        "Rolling Mill Stand RM-401 – Central Lubrication Pump Unit",
        "Rolling Mill Stand RM-401",
        "Rolling Mill Stand",
        "Metals / Rolling",
    ),
    5: _CuratedMachine(  # L1-E915-M005, CRUSHER — low lubricant / reservoir availability
        "Primary Gyratory Crusher CR-101 – Lubrication System",
        "Primary Gyratory Crusher CR-101",
        "Primary Gyratory Crusher",
        "Crushing",
    ),
    8: _CuratedMachine(  # L2-E915-M008, FAN — independent bearing-condition deterioration
        "Kiln ID Fan IDF-01 – Drive-End Bearing",
        "Kiln ID Fan IDF-01",
        "Kiln ID Fan",
        "Pyroprocessing",
    ),
    9: _CuratedMachine(  # L1-07A8-M009, PUMP — possible leakage / lubricant delivery loss
        "Ball Mill BM-301 – Pinion Bearing Lubrication Circuit",
        "Ball Mill BM-301",
        "Ball Mill",
        "Grinding",
    ),
    12: _CuratedMachine(  # L2-07A8-M012, CONVEYOR — active developing restriction
        "Stacker-Reclaimer SR-201 – Slew Bearing Lubrication Circuit",
        "Stacker-Reclaimer SR-201",
        "Stacker-Reclaimer",
        "Bulk Material Handling",
    ),
    13: _CuratedMachine(  # L1-95FA-M013, MOTOR — sensor / data-quality limitation
        "Apron Feeder AF-101 – Head Shaft Lubrication Circuit",
        "Apron Feeder AF-101",
        "Apron Feeder",
        "Bulk Material Handling",
    ),
    16: _CuratedMachine(  # L1-7F84-M016, COMPRESSOR — recently maintained / recovering
        "Bucket Elevator BE-201 – Head Shaft Bearings",
        "Bucket Elevator BE-201",
        "Bucket Elevator",
        "Bulk Material Handling",
    ),
    17: _CuratedMachine(  # L1-7F84-M017, CRUSHER — commissioning / insufficient evidence
        "Secondary Crusher CR-202 – Main Bearing Lubrication Circuit",
        "Secondary Crusher CR-202",
        "Secondary Crusher",
        "Crushing",
    ),
}


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
    generic_name = f"{machine_type.value.title()} {index:03d}"
    curated = CURATED_MACHINE_NAMES.get(index)
    display_name = curated.display_name if curated else generic_name
    short_label = curated.short_label if curated else generic_name
    machine_metadata: dict[str, Any] = {"demo": True}
    if curated:
        machine_metadata["equipment_class"] = curated.equipment_class
        machine_metadata["area"] = curated.area

    machine = await get_or_create(
        session,
        Machine,
        det_id("machine", str(index)),
        tenant_id=tenant_id,
        production_line_id=line.id,
        name=display_name,
        asset_code=asset_code,
        machine_type=machine_type,
        manufacturer=manufacturer_for(index),
        model=f"{machine_type.value[:2].upper()}-{100 + index}",
        serial_number_demo=f"DEMO-SN-{index:05d}",
        installation_date=BASE_DATE + timedelta(days=index * 11),
        criticality=CRITICALITY_CYCLE[(index + 1) % len(CRITICALITY_CYCLE)],
        operating_profile={"duty_cycle": "continuous" if index % 2 == 0 else "intermittent"},
        status=MachineStatus.REGISTERED if equipment_tier == 3 else MachineStatus.MONITORED,
        metadata_=machine_metadata,
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
            name=f"{short_label} — {position.replace('_', ' ').title()} Bearing",
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

    await seed_lubrication_system(session, tenant_id, machine, bearings, index, short_label)


async def seed_lubrication_system(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    machine: Machine,
    bearings: list[Bearing],
    index: int,
    short_label: str,
) -> None:
    system_type = list(LubricationSystemType)[index % len(list(LubricationSystemType))]
    system = await get_or_create(
        session,
        LubricationSystem,
        det_id("lubsys", str(index)),
        tenant_id=tenant_id,
        machine_id=machine.id,
        name=f"{short_label} Lubrication System",
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
        name=f"{short_label} Reservoir",
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
        name=f"{short_label} Pump",
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
        name=f"{short_label} Controller",
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
        name=f"{short_label} Distributor",
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
            name=f"{short_label} Circuit {circuit_index + 1}",
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
        name=f"{short_label} RPM Sensor",
        sensor_type=SensorType.RPM,
        unit="rpm",
        installation_date=machine.installation_date,
        status=SensorStatus.ACTIVE,
        quality_state=SensorQualityState.UNKNOWN,
        machine_id=machine.id,
        metadata_={"demo": True},
    )
    # Machine driveline power (Lubrication Efficiency Intelligence, Pass 1 —
    # docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176) — deliberately machine-direct
    # like RPM above, and deliberately NOT the same sensor as PUMP_CURRENT (that measures
    # the lubrication pump's own small motor, not this machine's driveline). Registered
    # for every machine so the fleet's sensor inventory is structurally consistent; only
    # a subset of scenario scripts actually write meaningful telemetry for it in this
    # pass (see the design doc's representative-machine list) — an unwritten-to sensor is
    # a real, honest INSUFFICIENT_DATA state, not a gap to hide.
    await get_or_create(
        session,
        Sensor,
        det_id("sensor", "power", str(index)),
        tenant_id=tenant_id,
        sensor_code=f"PWR-{machine.id.hex[:8]}",
        name=f"{short_label} Power Sensor",
        sensor_type=SensorType.MACHINE_POWER,
        unit="kW",
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
