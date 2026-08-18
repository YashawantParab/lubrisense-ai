from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.domain.enums import SensorQualityState, SensorStatus, SensorType

# Mirrors app.domain.models._SENSOR_ATTACHMENT_COLUMNS — kept in sync deliberately
# rather than imported, since this is API response shape, not ORM internals.
_ATTACHMENT_FIELDS = (
    "machine_id",
    "bearing_id",
    "lubrication_system_id",
    "reservoir_id",
    "pump_id",
    "circuit_id",
)


class SensorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sensor_code: str
    name: str
    sensor_type: SensorType
    unit: str | None
    installation_date: date | None
    calibration_date: date | None
    firmware_version: str | None
    status: SensorStatus
    quality_state: SensorQualityState
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime

    machine_id: uuid.UUID | None
    bearing_id: uuid.UUID | None
    lubrication_system_id: uuid.UUID | None
    reservoir_id: uuid.UUID | None
    pump_id: uuid.UUID | None
    circuit_id: uuid.UUID | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def attached_entity_type(self) -> str:
        """Which physical entity this sensor is attached to — one of `_ATTACHMENT_FIELDS`
        with its `_id` suffix stripped. Exactly one is always set (enforced by
        `ck_sensor_exactly_one_attachment`)."""
        for field_name in _ATTACHMENT_FIELDS:
            if getattr(self, field_name) is not None:
                return field_name.removesuffix("_id")
        raise ValueError("Sensor response has no attachment set")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def attached_entity_id(self) -> uuid.UUID:
        for field_name in _ATTACHMENT_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                return value  # type: ignore[no-any-return]
        raise ValueError("Sensor response has no attachment set")
