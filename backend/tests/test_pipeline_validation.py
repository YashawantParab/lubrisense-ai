"""Unit tests for `app.pipeline.validation.SchemaValidator` — pure, no database needed."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from app.domain.enums import QuarantineReason
from app.pipeline.validation import SchemaValidator, ValidatedTelemetry, ValidationFailure


def _valid_envelope(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    base: dict[str, object] = {
        "event_id": str(uuid.uuid4()),
        "schema_version": "1",
        "correlation_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "machine_id": str(uuid.uuid4()),
        "sensor_id": str(uuid.uuid4()),
        "measurement_type": "PRESSURE",
        "value": 4.2,
        "unit": "bar",
        "quality": "GOOD",
        "operating_state": "RUNNING_NORMAL_LOAD",
        "source_timestamp": now,
        "edge_received_timestamp": now,
        "sequence_number": 1,
        "gateway_id": "GW-TEST",
        "device_id": "sim-device",
        "source": "synthetic",
    }
    base.update(overrides)
    return base


def _validator(supported: set[str] | None = None) -> SchemaValidator:
    return SchemaValidator(supported or {"1"})


def test_valid_envelope_parses() -> None:
    raw = json.dumps(_valid_envelope()).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidatedTelemetry)
    assert result.measurement_type == "PRESSURE"
    assert result.value == 4.2


def test_malformed_json_is_schema_invalid() -> None:
    result = _validator().validate(b"{not json")
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.SCHEMA_INVALID


def test_non_object_json_is_schema_invalid() -> None:
    result = _validator().validate(b"[1, 2, 3]")
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.SCHEMA_INVALID


def test_missing_required_field_is_schema_invalid() -> None:
    envelope = _valid_envelope()
    del envelope["sensor_id"]
    raw = json.dumps(envelope).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.SCHEMA_INVALID
    assert "sensor_id" in result.detail


def test_invalid_uuid_is_schema_invalid() -> None:
    raw = json.dumps(_valid_envelope(tenant_id="not-a-uuid")).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.SCHEMA_INVALID


def test_invalid_timestamp_is_schema_invalid() -> None:
    raw = json.dumps(_valid_envelope(source_timestamp="")).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.SCHEMA_INVALID


def test_unknown_measurement_type_is_schema_invalid() -> None:
    raw = json.dumps(_valid_envelope(measurement_type="NOT_A_TYPE")).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.SCHEMA_INVALID


def test_unknown_quality_is_schema_invalid() -> None:
    raw = json.dumps(_valid_envelope(quality="WEIRD")).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.SCHEMA_INVALID


def test_negative_sequence_number_is_schema_invalid() -> None:
    raw = json.dumps(_valid_envelope(sequence_number=-1)).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.SCHEMA_INVALID


def test_unsupported_schema_version_is_rejected_distinctly() -> None:
    raw = json.dumps(_valid_envelope(schema_version="99")).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidationFailure)
    assert result.reason == QuarantineReason.UNSUPPORTED_SCHEMA_VERSION


def test_optional_hierarchy_fields_may_be_absent() -> None:
    raw = json.dumps(_valid_envelope()).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidatedTelemetry)
    assert result.site_id is None
    assert result.bearing_id is None
    assert result.lubrication_point_id is None


def test_event_id_and_sequence_number_preserved_exactly() -> None:
    event_id = str(uuid.uuid4())
    raw = json.dumps(_valid_envelope(event_id=event_id, sequence_number=42)).encode("utf-8")
    result = _validator().validate(raw)
    assert isinstance(result, ValidatedTelemetry)
    assert str(result.event_id) == event_id
    assert result.sequence_number == 42
