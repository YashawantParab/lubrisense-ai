"""Test doubles that avoid a live database dependency for pure edge-logic unit tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from edge.acquisition.source import RawObservation

TENANT_ID = uuid.UUID("bbdd114e-b5a7-5890-a5bd-9e8c787a5fe0")
MACHINE_ID = uuid.UUID("88551bef-3149-5a8d-9645-bcd9502f4795")
PRESSURE_SENSOR_ID = uuid.uuid5(MACHINE_ID, "PRESSURE")
RESERVOIR_SENSOR_ID = uuid.uuid5(MACHINE_ID, "RESERVOIR_LEVEL")
PUMP_CURRENT_SENSOR_ID = uuid.uuid5(MACHINE_ID, "PUMP_CURRENT")
BEARING_TEMP_SENSOR_ID = uuid.uuid5(MACHINE_ID, "BEARING_TEMPERATURE")


def make_observation(
    measurement_type: str = "PRESSURE",
    value: float | None = 5.0,
    quality: str = "GOOD",
    sensor_id: uuid.UUID | None = None,
    unit: str = "bar",
    operating_state: str = "RUNNING_NORMAL_LOAD",
    source_timestamp: datetime | None = None,
) -> RawObservation:
    return RawObservation(
        source_timestamp=source_timestamp or datetime.now(UTC),
        tenant_id=TENANT_ID,
        machine_id=MACHINE_ID,
        component_id=MACHINE_ID,
        sensor_id=sensor_id or PRESSURE_SENSOR_ID,
        measurement_type=measurement_type,
        value=value,
        unit=unit,
        quality=quality,
        operating_state=operating_state,
    )


class FakeTelemetrySource:
    """Yields pre-scripted ticks (each a list of `RawObservation`) — one `poll()` per tick."""

    def __init__(self, ticks: list[list[RawObservation]]) -> None:
        self._ticks: Iterator[list[RawObservation]] = iter(ticks)
        self.closed = False
        self.sensor_count = 4

    def poll(self) -> list[RawObservation]:
        try:
            return next(self._ticks)
        except StopIteration:
            return []

    def close(self) -> None:
        self.closed = True


def healthy_tick(t: int = 0, base_time: datetime | None = None) -> list[RawObservation]:
    ts = (base_time or datetime.now(UTC)) + timedelta(seconds=5 * t)
    return [
        make_observation("PRESSURE", 8.0, "GOOD", PRESSURE_SENSOR_ID, "bar", source_timestamp=ts),
        make_observation(
            "RESERVOIR_LEVEL", 80.0, "GOOD", RESERVOIR_SENSOR_ID, "percent", source_timestamp=ts
        ),
        make_observation(
            "PUMP_CURRENT", 5.0, "GOOD", PUMP_CURRENT_SENSOR_ID, "A", source_timestamp=ts
        ),
    ]
