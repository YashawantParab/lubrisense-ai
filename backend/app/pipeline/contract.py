"""The central pipeline's own copy of the edge's wire contract.

Mirrors `edge.domain.envelope.ReadingEnvelope` field-for-field, but is defined
independently rather than imported from the `edge` package (TECHNICAL_DECISIONS.md
ADR-059) — the two services stay independently deployable, and the central pipeline is
not coupled to the edge's internal module layout. The wire *values* must still match
exactly, since real bytes cross this boundary unchanged (see `docs/TELEMETRY_PIPELINE.md`).

`TelemetryEnvelope` is intentionally permissive at the type level (most fields are
plain `str`/`Any`, not strict UUID/enum types) — that stricter validation is
`SchemaValidator`'s job (see `validation.py`), which distinguishes "structurally
malformed, route to DLQ" from "well-formed JSON with an out-of-range value" and reports a
precise reason either way, rather than letting pydantic raise an opaque error.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

SUPPORTED_MEASUREMENT_TYPES = frozenset(
    {
        "PRESSURE",
        "FLOW",
        "RESERVOIR_LEVEL",
        "PUMP_CURRENT",
        "PUMP_RUNTIME",
        "CYCLE_COMPLETION",
        "PISTON_MOVEMENT",
        "LUBRICANT_TEMPERATURE",
        "VIBRATION_RMS",
        "VIBRATION_PEAK",
        "BEARING_TEMPERATURE",
        "RPM",
        "LOAD",
    }
)

SUPPORTED_QUALITIES = frozenset(
    {
        "GOOD",
        "UNCERTAIN",
        "SUSPECT",
        "MISSING",
        "INVALID",
        "COMMUNICATION_LOSS",
        "BAD",
        "UNAVAILABLE",
    }
)

# Hierarchy fields the edge may leave null (SchemaValidator does not require these; the
# consumer's ContextEnrichmentService fills them in from the authoritative asset hierarchy).
OPTIONAL_HIERARCHY_FIELDS = (
    "site_id",
    "plant_id",
    "line_id",
    "bearing_id",
    "lubrication_system_id",
    "circuit_id",
    "lubrication_point_id",
    "component_id",
)


class TelemetryEnvelope(BaseModel):
    """Raw parse of the wire JSON — every field kept loose (`str`/`Any`) so a structurally
    present-but-invalid value (bad UUID, unknown enum) is caught by `SchemaValidator` with a
    specific reason, not by an opaque pydantic `ValidationError` at parse time."""

    model_config = ConfigDict(extra="allow")

    event_id: str | None = None
    schema_version: str | None = None
    correlation_id: str | None = None

    tenant_id: str | None = None
    site_id: str | None = None
    plant_id: str | None = None
    line_id: str | None = None
    machine_id: str | None = None
    bearing_id: str | None = None
    lubrication_system_id: str | None = None
    circuit_id: str | None = None
    lubrication_point_id: str | None = None
    component_id: str | None = None
    sensor_id: str | None = None

    measurement_type: str | None = None
    value: float | None = None
    unit: str | None = None
    quality: str | None = None
    operating_state: str | None = None

    source_timestamp: str | None = None
    edge_received_timestamp: str | None = None
    edge_emitted_timestamp: str | None = None

    sequence_number: int | None = None
    gateway_id: str | None = None
    device_id: str | None = None
    firmware_version: str | None = None
    controller_version: str | None = None
    source: str | None = None
    metadata: dict[str, Any] | None = None
