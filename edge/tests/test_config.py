from __future__ import annotations

import pytest
from pydantic import ValidationError

from edge.config.loader import load_edge_config
from edge.config.models import (
    BufferConfig,
    EdgeConfig,
    RangeThreshold,
    RuleThresholds,
    TransportConfig,
)


def _minimal(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "config_version": "1",
        "gateway_id": "gw-1",
        "gateway_code": "GW-TEST",
        "tenant_id": "tenant-1",
        "asset_code": "L1-7B43-M000",
    }
    base.update(overrides)
    return base


def test_default_config_loads_and_validates() -> None:
    config = load_edge_config()
    assert config.gateway_code == "GW-RIDGE-CRUSH"
    assert (
        config.resolved_topic() == f"lubrisense/v1/{config.tenant_id}/{config.gateway_id}/telemetry"
    )


def test_negative_poll_interval_rejected() -> None:
    with pytest.raises(ValidationError):
        EdgeConfig.model_validate(_minimal(poll_interval_seconds=-1.0))


def test_zero_poll_interval_rejected() -> None:
    with pytest.raises(ValidationError):
        EdgeConfig.model_validate(_minimal(poll_interval_seconds=0.0))


def test_empty_gateway_id_rejected() -> None:
    with pytest.raises(ValidationError):
        EdgeConfig.model_validate(_minimal(gateway_id="  "))


def test_invalid_retention_count_rejected() -> None:
    with pytest.raises(ValidationError):
        BufferConfig.model_validate({"max_buffered_events": 0})


def test_invalid_retention_age_rejected() -> None:
    with pytest.raises(ValidationError):
        BufferConfig.model_validate({"max_buffer_age_seconds": -5.0})


def test_unknown_measurement_type_in_enabled_list_rejected() -> None:
    with pytest.raises(ValidationError):
        EdgeConfig.model_validate(_minimal(enabled_measurement_types=["NOT_A_REAL_TYPE"]))


def test_unknown_measurement_type_in_range_threshold_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleThresholds.model_validate(
            {
                "range_thresholds": [
                    {"measurement_type": "NOT_A_TYPE", "min_value": 0, "max_value": 1}
                ]
            }
        )


def test_duplicate_range_threshold_entries_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleThresholds.model_validate(
            {
                "range_thresholds": [
                    {"measurement_type": "PRESSURE", "min_value": 0, "max_value": 10},
                    {"measurement_type": "PRESSURE", "min_value": 0, "max_value": 20},
                ]
            }
        )


def test_range_threshold_min_must_be_below_max() -> None:
    with pytest.raises(ValidationError):
        RangeThreshold.model_validate(
            {"measurement_type": "PRESSURE", "min_value": 10, "max_value": 5}
        )


def test_invalid_topic_template_missing_placeholders_rejected() -> None:
    with pytest.raises(ValidationError):
        TransportConfig.model_validate({"topic_template": "lubrisense/v1/telemetry"})


def test_topic_template_missing_only_gateway_placeholder_rejected() -> None:
    with pytest.raises(ValidationError):
        TransportConfig.model_validate({"topic_template": "lubrisense/v1/{tenant_id}/telemetry"})


def test_invalid_transport_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        TransportConfig.model_validate({"mode": "carrier-pigeon"})


def test_invalid_qos_rejected() -> None:
    with pytest.raises(ValidationError):
        TransportConfig.model_validate({"qos": 5})


def test_sensor_fault_debounce_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        RuleThresholds.model_validate({"sensor_fault_debounce_ticks": 0})


def test_config_is_frozen() -> None:
    config = EdgeConfig.model_validate(_minimal())
    with pytest.raises(ValidationError):
        config.gateway_id = "changed"  # type: ignore[misc]
