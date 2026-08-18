"""Shared builders for Phase 7 rule unit tests — every rule is a pure function, so these
tests never touch a database (Phase 7 brief §60)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.data_quality.config.policy import QualityPolicy
from app.data_quality.domain.context import SensorContext, SensorInfo, TelemetryPoint
from app.pipeline.validation import ValidatedTelemetry

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
SENSOR_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
MACHINE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def make_event(**overrides: Any) -> ValidatedTelemetry:
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "event_id": uuid.uuid4(),
        "schema_version": "1",
        "correlation_id": str(uuid.uuid4()),
        "tenant_id": TENANT_ID,
        "site_id": None,
        "plant_id": None,
        "line_id": None,
        "machine_id": MACHINE_ID,
        "bearing_id": None,
        "lubrication_system_id": None,
        "circuit_id": None,
        "lubrication_point_id": None,
        "component_id": None,
        "sensor_id": SENSOR_ID,
        "measurement_type": "PRESSURE",
        "value": 4.2,
        "unit": "bar",
        "quality": "GOOD",
        "operating_state": "RUNNING_NORMAL_LOAD",
        "source_timestamp": now,
        "edge_received_timestamp": now,
        "edge_emitted_timestamp": None,
        "sequence_number": 1,
        "gateway_id": "GW-TEST",
        "device_id": "test-device",
        "firmware_version": None,
        "controller_version": None,
        "source": "synthetic",
        "metadata": {},
    }
    base.update(overrides)
    return ValidatedTelemetry(**base)


def make_context(**overrides: Any) -> SensorContext:
    base = SensorContext.initial(TENANT_ID, SENSOR_ID)
    return SensorContext(**{**base.__dict__, **overrides})


def make_sensor_info(**overrides: Any) -> SensorInfo:
    base: dict[str, Any] = {"sensor_type": "PRESSURE", "unit": "bar"}
    base.update(overrides)
    return SensorInfo(**base)


def make_point(**overrides: Any) -> TelemetryPoint:
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "event_id": uuid.uuid4(),
        "sensor_id": SENSOR_ID,
        "source_timestamp": now,
        "persisted_timestamp": now,
        "mqtt_received_timestamp": now,
        "value": 4.2,
        "quality": "GOOD",
        "operating_state": "RUNNING_NORMAL_LOAD",
        "measurement_type": "PRESSURE",
        "sequence_number": 1,
    }
    base.update(overrides)
    return TelemetryPoint(**base)


def make_policy(**overrides: Any) -> QualityPolicy:
    base: dict[str, Any] = {
        "policy_version": "test",
        "eligibility_mapping": {
            "NONE": {"quality_state": "TRUSTED", "eligibility": "ELIGIBLE"},
            "INFO": {"quality_state": "TRUSTED", "eligibility": "ELIGIBLE"},
            "WARNING": {
                "quality_state": "USABLE_WITH_CAUTION",
                "eligibility": "ELIGIBLE_WITH_CAUTION",
            },
            "ERROR": {"quality_state": "UNUSABLE", "eligibility": "INELIGIBLE"},
            "CRITICAL": {"quality_state": "UNUSABLE", "eligibility": "INELIGIBLE"},
        },
        "validity": {
            "value_ranges": {"PRESSURE": (0.0, 25.0), "RPM": (0.0, 10000.0)},
            "expected_unit": {"PRESSURE": "bar", "RPM": "rpm"},
        },
    }
    base.update(overrides)
    return QualityPolicy.model_validate(base)
