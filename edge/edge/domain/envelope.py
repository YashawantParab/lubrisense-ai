"""`ReadingEnvelope` — the edge's own event contract (Phase 5 brief §3).

Carries the full asset context a `TelemetryReading` will eventually need
(docs/EVENT_CATALOG.md §2.1), but does not force-populate fields the edge cannot honestly
resolve: `SimulatorTelemetrySource` only has `tenant_id`/`machine_id`/`component_id`/
`sensor_id` from `simulator.domain.topology.MachineTopology` — `site_id`/`plant_id`/
`line_id`/`bearing_id`/`lubrication_system_id`/`circuit_id`/`lubrication_point_id` stay
`None` here rather than being guessed. `value`/`quality` are taken from
`SimulationReading.observed_value`/`quality` only — never `true_value`
(docs/SYNTHETIC_DATA_MODEL.md §3).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from edge.domain.enums import EdgeMeasurementType, EdgeQuality

SCHEMA_VERSION = "1"

# Fixed namespace for deterministic event-id derivation (ADR-045). Any valid UUID works as a
# uuid5 namespace; this one is arbitrary but must never change once events have been emitted.
EDGE_EVENT_NAMESPACE = uuid.UUID("5f1a2b3c-4d5e-4f60-8a1b-2c3d4e5f6071")


def make_event_id(gateway_id: str, sensor_id: str, sequence_number: int) -> str:
    """Deterministic, unique event id (ADR-045) — not timestamp-based. Generated once at
    acquisition time and never regenerated on retry/replay, which is what makes replay
    idempotent: resending the same buffered row always carries the same `event_id`."""
    return str(uuid.uuid5(EDGE_EVENT_NAMESPACE, f"{gateway_id}|{sensor_id}|{sequence_number}"))


class ReadingEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    schema_version: str = SCHEMA_VERSION
    correlation_id: str

    tenant_id: uuid.UUID
    site_id: uuid.UUID | None = None
    plant_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None
    machine_id: uuid.UUID
    bearing_id: uuid.UUID | None = None
    lubrication_system_id: uuid.UUID | None = None
    circuit_id: uuid.UUID | None = None
    lubrication_point_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    sensor_id: uuid.UUID

    measurement_type: EdgeMeasurementType
    value: float | None
    unit: str
    quality: EdgeQuality
    operating_state: str

    source_timestamp: datetime
    edge_received_timestamp: datetime
    edge_emitted_timestamp: datetime | None = None

    sequence_number: int
    gateway_id: str
    device_id: str
    firmware_version: str | None = None
    controller_version: str | None = None
    source: str = "synthetic"
    metadata: dict[str, Any] = {}

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> ReadingEnvelope:
        return cls.model_validate_json(raw)

    def with_emitted_now(self, emitted: datetime) -> ReadingEnvelope:
        return self.model_copy(update={"edge_emitted_timestamp": emitted})


def dumps_for_transport(envelope: ReadingEnvelope) -> bytes:
    return json.dumps(json.loads(envelope.to_json()), separators=(",", ":")).encode("utf-8")
