"""Plain-data snapshots rules operate on — never live ORM objects, so every rule stays a
pure function testable without a database (Phase 7 brief §60's "unit tests... no DB")."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import ClockStatus, Eligibility, QualityState, StalenessStatus


@dataclass(frozen=True)
class SensorContext:
    """A sensor's prior state, as of just before the current event/window is evaluated —
    built from `SensorQualityState` (or `.initial(...)` for a sensor seen for the first
    time)."""

    tenant_id: uuid.UUID
    sensor_id: uuid.UUID
    machine_id: uuid.UUID | None
    quality_state: QualityState
    eligibility: Eligibility
    last_good_reading_at: datetime | None
    last_good_reading_value: float | None
    last_observed_at: datetime | None
    last_observed_value: float | None
    last_observed_quality: str | None
    last_observed_operating_state: str | None
    last_source_timestamp_seen: datetime | None
    expected_next_sequence: int | None
    staleness_status: StalenessStatus
    clock_status: ClockStatus
    active_issue_count: int
    firmware_version: str | None
    controller_version: str | None

    @classmethod
    def initial(cls, tenant_id: uuid.UUID, sensor_id: uuid.UUID) -> SensorContext:
        return cls(
            tenant_id=tenant_id,
            sensor_id=sensor_id,
            machine_id=None,
            quality_state=QualityState.TRUSTED,
            eligibility=Eligibility.ELIGIBLE,
            last_good_reading_at=None,
            last_good_reading_value=None,
            last_observed_at=None,
            last_observed_value=None,
            last_observed_quality=None,
            last_observed_operating_state=None,
            last_source_timestamp_seen=None,
            expected_next_sequence=None,
            staleness_status=StalenessStatus.UNKNOWN,
            clock_status=ClockStatus.UNKNOWN,
            active_issue_count=0,
            firmware_version=None,
            controller_version=None,
        )


@dataclass(frozen=True)
class SensorInfo:
    """The subset of `Sensor` (Phase 2 domain) that quality rules need — kept separate
    from the ORM model for the same pure-function-testability reason as `SensorContext`."""

    sensor_type: str
    unit: str | None


@dataclass(frozen=True)
class TelemetryPoint:
    """One row of `telemetry` history, as window-level rules need it — built from a
    `TelemetryRepository.get_by_sensor_time_range`/`get_by_machine_time_range` query
    result. `sensor_id` is redundant for sensor-scoped window queries but lets the same
    dataclass serve machine-level aggregation (e.g. communication-loss incidence across
    every sensor on a machine) without a second, near-identical type."""

    event_id: uuid.UUID
    sensor_id: uuid.UUID
    source_timestamp: datetime
    persisted_timestamp: datetime
    mqtt_received_timestamp: datetime
    value: float | None
    quality: str
    operating_state: str
    measurement_type: str
    sequence_number: int
