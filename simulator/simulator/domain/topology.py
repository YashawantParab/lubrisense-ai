"""Read-only asset topology — the simulator's view of the Phase 2 Postgres schema.

These dataclasses carry only the fields the simulator needs (ids, names, and the handful
of attributes that shape physical behavior, e.g. `machine_type`, `capacity_demo`). They are
NOT a copy of the domain model; they are populated by `simulator.engine.repository` from
live queries against the same database Phase 2 seeded, never hardcoded (Phase 3 brief §2:
"do not create a separate disconnected asset universe").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SensorTopology:
    id: uuid.UUID
    sensor_code: str
    sensor_type: str
    unit: str | None
    attached_entity_type: str
    attached_entity_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class BearingTopology:
    id: uuid.UUID
    name: str
    position: str
    criticality: str


@dataclass(frozen=True, slots=True)
class ReservoirTopology:
    id: uuid.UUID
    name: str
    capacity_demo: float | None
    capacity_unit: str | None


@dataclass(frozen=True, slots=True)
class PumpTopology:
    id: uuid.UUID
    name: str
    pump_type: str | None


@dataclass(frozen=True, slots=True)
class ControllerTopology:
    id: uuid.UUID
    name: str
    controller_type: str | None


@dataclass(frozen=True, slots=True)
class DistributorTopology:
    id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class LubricationPointTopology:
    id: uuid.UUID
    code: str
    bearing_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class CircuitTopology:
    id: uuid.UUID
    code: str
    lubrication_points: tuple[LubricationPointTopology, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class LubricationSystemTopology:
    id: uuid.UUID
    name: str
    system_type: str
    reservoir: ReservoirTopology
    pump: PumpTopology
    controller: ControllerTopology
    distributor: DistributorTopology | None
    circuits: tuple[CircuitTopology, ...]


@dataclass(frozen=True, slots=True)
class MachineTopology:
    """The unit of simulation. One `MachineTopology` carries everything the
    `SimulationEngine` needs to derive a full lubrication chain + bearing set + attached
    sensors for one asset, resolved from real Phase 2 ids — see
    `simulator.engine.repository.load_machine_topology`."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    asset_code: str
    machine_type: str
    criticality: str
    bearings: tuple[BearingTopology, ...]
    lubrication_system: LubricationSystemTopology | None
    sensors: tuple[SensorTopology, ...]

    def sensors_of_type(self, measurement_type: str) -> tuple[SensorTopology, ...]:
        return tuple(s for s in self.sensors if s.sensor_type == measurement_type)
