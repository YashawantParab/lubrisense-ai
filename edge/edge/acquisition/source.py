"""`TelemetrySource` — the clean adapter boundary between the edge and whatever produces
sensor readings (Phase 5 brief §2). `SimulatorTelemetrySource` drives Phase 3/4's
`SimulationEngine` **in-process** (no shelling out to the simulator CLI, no re-implemented
physics — the whole point of this boundary is that the edge never duplicates simulator
logic). A future `FutureRealDeviceTelemetrySource` would read from an actual PLC/gateway
protocol; it is intentionally unimplemented here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from simulator.config.loader import load_engineering_config
from simulator.engine.repository import TopologyRepository
from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios.instance import ScenarioInstance


@dataclass(frozen=True, slots=True)
class RawObservation:
    """What a `TelemetrySource` hands to the edge acquisition loop — deliberately narrower
    than `simulator.engine.output.SimulationReading`: only `observed_value`/`quality` cross
    this boundary, never `true_value` (docs/SYNTHETIC_DATA_MODEL.md §3)."""

    source_timestamp: datetime
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID
    sensor_id: uuid.UUID
    measurement_type: str
    value: float | None
    unit: str
    quality: str
    operating_state: str


class TelemetrySource(Protocol):
    def poll(self) -> list[RawObservation]:
        """One acquisition cycle's worth of readings."""
        ...

    def close(self) -> None: ...


class SimulatorTelemetrySource:
    """Wraps `simulator.engine.simulation_engine.SimulationEngine` — one `poll()` call
    advances the simulation by one tick and returns that tick's observable readings."""

    def __init__(
        self,
        asset_code: str,
        seed: int = 42,
        step_seconds: float | None = None,
        database_url: str | None = None,
        config_path: Path | None = None,
        scenario_instances: list[ScenarioInstance] | None = None,
    ) -> None:
        engineering_config = load_engineering_config(config_path)
        repo = TopologyRepository(database_url=database_url)
        self._topology = repo.load_machine_topology(asset_code=asset_code)
        self._engine = SimulationEngine(
            topology=self._topology,
            config=engineering_config,
            seed=seed,
            start_time=datetime.now().astimezone(),
            step_seconds=step_seconds,
            scenario_instances=scenario_instances or [],
        )

    @property
    def sensor_count(self) -> int:
        return len(self._topology.sensors)

    def poll(self) -> list[RawObservation]:
        tick = self._engine.step()
        return [
            RawObservation(
                source_timestamp=r.simulation_timestamp,
                tenant_id=r.tenant_id,
                machine_id=r.asset_id,
                component_id=r.component_id,
                sensor_id=r.sensor_id,
                measurement_type=r.measurement_type,
                value=r.observed_value,
                unit=r.unit,
                quality=r.quality,
                operating_state=r.operating_state,
            )
            for r in tick.readings
        ]

    def close(self) -> None:
        pass


class FutureRealDeviceTelemetrySource:
    """Documents the intended real-device integration boundary (Phase 5 brief §2) — not
    implemented in this reference. A real implementation would read from an actual PLC/edge
    protocol (OPC-UA, Modbus, a vendor SDK, ...) and produce the same `RawObservation` shape,
    requiring no change to `edge.acquisition.builder`, `edge.buffering`, `edge.rules`, or
    `edge.transport`."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "FutureRealDeviceTelemetrySource is a documented integration boundary, not an "
            "implemented Phase 5 deliverable — see docs/EDGE_ARCHITECTURE.md "
            "'Future real-device integration'."
        )

    def poll(self) -> list[RawObservation]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
