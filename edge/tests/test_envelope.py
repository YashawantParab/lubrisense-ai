from __future__ import annotations

from edge.domain.envelope import ReadingEnvelope, make_event_id
from tests.fakes import MACHINE_ID, PRESSURE_SENSOR_ID, TENANT_ID


def _envelope(**overrides: object) -> ReadingEnvelope:
    base = {
        "event_id": make_event_id("gw-1", str(PRESSURE_SENSOR_ID), 1),
        "correlation_id": "corr-1",
        "tenant_id": TENANT_ID,
        "machine_id": MACHINE_ID,
        "sensor_id": PRESSURE_SENSOR_ID,
        "measurement_type": "PRESSURE",
        "value": 5.0,
        "unit": "bar",
        "quality": "GOOD",
        "operating_state": "RUNNING_NORMAL_LOAD",
        "source_timestamp": "2026-01-01T00:00:00+00:00",
        "edge_received_timestamp": "2026-01-01T00:00:01+00:00",
        "sequence_number": 1,
        "gateway_id": "gw-1",
        "device_id": "gw-1",
    }
    base.update(overrides)
    return ReadingEnvelope.model_validate(base)


def test_event_id_is_deterministic() -> None:
    a = make_event_id("gw-1", "sensor-1", 42)
    b = make_event_id("gw-1", "sensor-1", 42)
    assert a == b


def test_event_id_varies_by_sequence() -> None:
    a = make_event_id("gw-1", "sensor-1", 1)
    b = make_event_id("gw-1", "sensor-1", 2)
    assert a != b


def test_event_id_varies_by_sensor() -> None:
    a = make_event_id("gw-1", "sensor-1", 1)
    b = make_event_id("gw-1", "sensor-2", 1)
    assert a != b


def test_event_id_varies_by_gateway() -> None:
    a = make_event_id("gw-1", "sensor-1", 1)
    b = make_event_id("gw-2", "sensor-1", 1)
    assert a != b


def test_envelope_json_round_trip() -> None:
    envelope = _envelope()
    restored = ReadingEnvelope.from_json(envelope.to_json())
    assert restored == envelope


def test_envelope_optional_hierarchy_fields_default_to_none() -> None:
    envelope = _envelope()
    assert envelope.site_id is None
    assert envelope.plant_id is None
    assert envelope.line_id is None
    assert envelope.bearing_id is None


def test_envelope_null_value_survives_round_trip() -> None:
    envelope = _envelope(value=None, quality="MISSING")
    restored = ReadingEnvelope.from_json(envelope.to_json())
    assert restored.value is None
    assert restored.quality.value == "MISSING"


def test_with_emitted_now_is_immutable_update() -> None:
    envelope = _envelope()
    from datetime import UTC, datetime

    emitted = datetime.now(UTC)
    updated = envelope.with_emitted_now(emitted)
    assert envelope.edge_emitted_timestamp is None
    assert updated.edge_emitted_timestamp == emitted
