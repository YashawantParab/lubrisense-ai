from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import SensorType, TelemetryQuality


class TelemetryReadingResponse(BaseModel):
    """A single persisted telemetry reading. Deliberately does not expose Kafka
    partition/offset (internal consumer traceability metadata, not product-facing —
    brief §31)."""

    model_config = ConfigDict(from_attributes=True)

    event_id: uuid.UUID
    sensor_id: uuid.UUID
    machine_id: uuid.UUID | None
    bearing_id: uuid.UUID | None
    lubrication_system_id: uuid.UUID | None
    circuit_id: uuid.UUID | None

    measurement_type: SensorType
    value: float | None
    unit: str
    quality: TelemetryQuality
    operating_state: str

    source_timestamp: datetime
    persisted_timestamp: datetime

    gateway_id: str
    metadata_: dict[str, object] = Field(serialization_alias="metadata")
