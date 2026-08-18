"""Structural validation of the wire contract (Phase 6 brief §2/§13).

This is *structural* validation only — "is this a well-formed telemetry event" — not the
Phase 7 data-quality engine. A message that fails here can't be reasoned about at all
(bad JSON, missing required field, unparseable UUID/timestamp, unsupported
`schema_version`) and is routed to the Kafka DLQ topic by the caller (the MQTT bridge).
Tenant/entity/context validation is a separate, later step (`enrichment.py`) that requires
a database lookup the bridge deliberately does not have.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from app.domain.enums import QuarantineReason
from app.pipeline.contract import (
    SUPPORTED_MEASUREMENT_TYPES,
    SUPPORTED_QUALITIES,
    TelemetryEnvelope,
)

_REQUIRED_FIELDS = (
    "event_id",
    "correlation_id",
    "tenant_id",
    "machine_id",
    "sensor_id",
    "measurement_type",
    "unit",
    "quality",
    "operating_state",
    "source_timestamp",
    "edge_received_timestamp",
    "sequence_number",
    "gateway_id",
    "device_id",
    "source",
)

_UUID_FIELDS = (
    "event_id",
    "tenant_id",
    "site_id",
    "plant_id",
    "line_id",
    "machine_id",
    "bearing_id",
    "lubrication_system_id",
    "circuit_id",
    "lubrication_point_id",
    "component_id",
    "sensor_id",
)

_TIMESTAMP_FIELDS = ("source_timestamp", "edge_received_timestamp", "edge_emitted_timestamp")


@dataclass(frozen=True)
class ValidatedTelemetry:
    """A structurally sound event, with every field typed and parsed. Ready for
    `enrichment.ContextEnrichmentService` — nothing here has touched the database yet."""

    event_id: uuid.UUID
    schema_version: str
    correlation_id: str

    tenant_id: uuid.UUID
    site_id: uuid.UUID | None
    plant_id: uuid.UUID | None
    line_id: uuid.UUID | None
    machine_id: uuid.UUID
    bearing_id: uuid.UUID | None
    lubrication_system_id: uuid.UUID | None
    circuit_id: uuid.UUID | None
    lubrication_point_id: uuid.UUID | None
    component_id: uuid.UUID | None
    sensor_id: uuid.UUID

    measurement_type: str
    value: float | None
    unit: str
    quality: str
    operating_state: str

    source_timestamp: datetime
    edge_received_timestamp: datetime
    edge_emitted_timestamp: datetime | None

    sequence_number: int
    gateway_id: str
    device_id: str
    firmware_version: str | None
    controller_version: str | None
    source: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ValidationFailure:
    reason: QuarantineReason
    detail: str


ValidationResult = ValidatedTelemetry | ValidationFailure


def _parse_timestamp(raw: str) -> datetime:
    # Python 3.11+ `datetime.fromisoformat` accepts a trailing "Z"; pydantic's
    # `model_dump_json()` (what the edge actually sends) emits "Z" for UTC.
    return datetime.fromisoformat(raw)


class SchemaValidator:
    def __init__(self, supported_schema_versions: set[str]) -> None:
        self._supported_schema_versions = supported_schema_versions

    def validate(self, raw: bytes) -> ValidationResult:
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return ValidationFailure(QuarantineReason.SCHEMA_INVALID, f"invalid JSON: {exc}")

        if not isinstance(parsed, dict):
            return ValidationFailure(
                QuarantineReason.SCHEMA_INVALID, "payload is not a JSON object"
            )

        try:
            envelope = TelemetryEnvelope.model_validate(parsed)
        except ValidationError as exc:
            return ValidationFailure(QuarantineReason.SCHEMA_INVALID, f"schema mismatch: {exc}")

        missing = [f for f in _REQUIRED_FIELDS if getattr(envelope, f) is None]
        if missing:
            return ValidationFailure(
                QuarantineReason.SCHEMA_INVALID, f"missing required field(s): {missing}"
            )

        if envelope.schema_version not in self._supported_schema_versions:
            return ValidationFailure(
                QuarantineReason.UNSUPPORTED_SCHEMA_VERSION,
                f"unsupported schema_version {envelope.schema_version!r}; "
                f"supported: {sorted(self._supported_schema_versions)}",
            )

        uuid_values: dict[str, uuid.UUID | None] = {}
        for field in _UUID_FIELDS:
            raw_value = getattr(envelope, field)
            if raw_value is None:
                uuid_values[field] = None
                continue
            try:
                uuid_values[field] = uuid.UUID(raw_value)
            except ValueError:
                return ValidationFailure(
                    QuarantineReason.SCHEMA_INVALID,
                    f"invalid UUID in field {field!r}: {raw_value!r}",
                )

        timestamp_values: dict[str, datetime | None] = {}
        for field in _TIMESTAMP_FIELDS:
            raw_value = getattr(envelope, field)
            if raw_value is None:
                timestamp_values[field] = None
                continue
            try:
                timestamp_values[field] = _parse_timestamp(raw_value)
            except ValueError:
                return ValidationFailure(
                    QuarantineReason.SCHEMA_INVALID,
                    f"invalid timestamp in field {field!r}: {raw_value!r}",
                )

        assert envelope.measurement_type is not None  # noqa: S101 - required field, checked above
        if envelope.measurement_type not in SUPPORTED_MEASUREMENT_TYPES:
            return ValidationFailure(
                QuarantineReason.SCHEMA_INVALID,
                f"unknown measurement_type {envelope.measurement_type!r}",
            )
        assert envelope.quality is not None  # noqa: S101
        if envelope.quality not in SUPPORTED_QUALITIES:
            return ValidationFailure(
                QuarantineReason.SCHEMA_INVALID, f"unknown quality {envelope.quality!r}"
            )

        assert envelope.sequence_number is not None  # noqa: S101
        if envelope.sequence_number < 0:
            return ValidationFailure(
                QuarantineReason.SCHEMA_INVALID,
                f"negative sequence_number {envelope.sequence_number}",
            )

        # All required fields validated non-None above; the asserts satisfy mypy.
        assert envelope.event_id is not None  # noqa: S101
        assert envelope.correlation_id is not None  # noqa: S101
        assert envelope.unit is not None  # noqa: S101
        assert envelope.operating_state is not None  # noqa: S101
        assert timestamp_values["source_timestamp"] is not None  # noqa: S101
        assert timestamp_values["edge_received_timestamp"] is not None  # noqa: S101
        assert envelope.gateway_id is not None  # noqa: S101
        assert envelope.device_id is not None  # noqa: S101
        assert envelope.source is not None  # noqa: S101
        assert uuid_values["tenant_id"] is not None  # noqa: S101
        assert uuid_values["machine_id"] is not None  # noqa: S101
        assert uuid_values["sensor_id"] is not None  # noqa: S101
        assert uuid_values["event_id"] is not None  # noqa: S101

        return ValidatedTelemetry(
            event_id=uuid_values["event_id"],
            schema_version=envelope.schema_version,
            correlation_id=envelope.correlation_id,
            tenant_id=uuid_values["tenant_id"],
            site_id=uuid_values["site_id"],
            plant_id=uuid_values["plant_id"],
            line_id=uuid_values["line_id"],
            machine_id=uuid_values["machine_id"],
            bearing_id=uuid_values["bearing_id"],
            lubrication_system_id=uuid_values["lubrication_system_id"],
            circuit_id=uuid_values["circuit_id"],
            lubrication_point_id=uuid_values["lubrication_point_id"],
            component_id=uuid_values["component_id"],
            sensor_id=uuid_values["sensor_id"],
            measurement_type=envelope.measurement_type,
            value=envelope.value,
            unit=envelope.unit,
            quality=envelope.quality,
            operating_state=envelope.operating_state,
            source_timestamp=timestamp_values["source_timestamp"],
            edge_received_timestamp=timestamp_values["edge_received_timestamp"],
            edge_emitted_timestamp=timestamp_values["edge_emitted_timestamp"],
            sequence_number=envelope.sequence_number,
            gateway_id=envelope.gateway_id,
            device_id=envelope.device_id,
            firmware_version=envelope.firmware_version,
            controller_version=envelope.controller_version,
            source=envelope.source,
            metadata=envelope.metadata or {},
        )
