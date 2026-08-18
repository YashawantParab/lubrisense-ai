"""`EdgeConfig` — versioned edge configuration (Phase 5 brief §19-§22).

Fail-fast: every validator here raises before `EdgeRuntime` starts (§20) rather than
falling back to a silently-different behavior. Rule thresholds are DEMO SYNTHETIC
ENGINEERING ASSUMPTIONS — NOT VALIDATED PRODUCTION LIMITS, matching
`simulator/simulator/config/demo_engineering.yaml`'s disclaimer convention; a real
deployment must replace them with validated, asset-specific limits.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from edge.domain.enums import EdgeMeasurementType

TRANSPORT_MODES = ("noop", "test", "mqtt")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RangeThreshold(_Frozen):
    measurement_type: EdgeMeasurementType
    min_value: float
    max_value: float

    @model_validator(mode="after")
    def _check_bounds(self) -> RangeThreshold:
        if self.min_value >= self.max_value:
            raise ValueError(
                f"range threshold for {self.measurement_type}: min_value must be < max_value "
                f"(got min={self.min_value}, max={self.max_value})"
            )
        return self


class RuleThresholds(_Frozen):
    """DEMO SYNTHETIC ENGINEERING ASSUMPTIONS. NOT VALIDATED PRODUCTION LIMITS."""

    range_thresholds: list[RangeThreshold] = Field(default_factory=list)
    reservoir_critical_percent: float = 10.0
    pump_running_current_a: float = 1.0
    pressure_near_zero_bar: float = 0.2
    lubrication_cycle_failure_seconds: float = 900.0
    critical_measurement_types: list[EdgeMeasurementType] = Field(default_factory=list)
    sensor_fault_debounce_ticks: int = 3

    @field_validator("range_thresholds")
    @classmethod
    def _no_duplicate_measurement_types(cls, value: list[RangeThreshold]) -> list[RangeThreshold]:
        seen: set[EdgeMeasurementType] = set()
        for entry in value:
            if entry.measurement_type in seen:
                raise ValueError(
                    f"duplicate range_threshold entry for measurement_type "
                    f"{entry.measurement_type!r} — each measurement type may only be "
                    "configured once"
                )
            seen.add(entry.measurement_type)
        return value

    @field_validator("sensor_fault_debounce_ticks")
    @classmethod
    def _debounce_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sensor_fault_debounce_ticks must be >= 1")
        return value


class BufferConfig(_Frozen):
    db_path: str = "./data/edge/{gateway_id}.db"
    max_buffered_events: int = 100_000
    max_buffer_age_seconds: float = 7 * 24 * 3600

    @field_validator("max_buffered_events")
    @classmethod
    def _max_events_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_buffered_events must be > 0")
        return value

    @field_validator("max_buffer_age_seconds")
    @classmethod
    def _max_age_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("max_buffer_age_seconds must be > 0")
        return value


class TransportConfig(_Frozen):
    mode: str = "noop"
    broker_host: str = "localhost"
    broker_port: int = 1883
    topic_template: str = "lubrisense/v1/{tenant_id}/{gateway_id}/telemetry"
    qos: int = 1
    client_id: str | None = None

    @field_validator("mode")
    @classmethod
    def _valid_mode(cls, value: str) -> str:
        if value not in TRANSPORT_MODES:
            raise ValueError(f"transport mode must be one of {TRANSPORT_MODES}, got {value!r}")
        return value

    @field_validator("topic_template")
    @classmethod
    def _topic_has_placeholders(cls, value: str) -> str:
        if "{tenant_id}" not in value or "{gateway_id}" not in value:
            raise ValueError(
                "topic_template must contain both {tenant_id} and {gateway_id} placeholders, "
                f"got {value!r}"
            )
        return value

    @field_validator("qos")
    @classmethod
    def _valid_qos(cls, value: int) -> int:
        if value not in (0, 1, 2):
            raise ValueError(f"qos must be 0, 1, or 2, got {value}")
        return value


class EdgeConfig(_Frozen):
    config_version: str
    gateway_id: str
    gateway_code: str
    tenant_id: str
    asset_code: str
    poll_interval_seconds: float = 5.0
    enabled_measurement_types: list[EdgeMeasurementType] | None = None
    rule_thresholds: RuleThresholds = Field(default_factory=RuleThresholds)
    buffer: BufferConfig = Field(default_factory=BufferConfig)
    transport: TransportConfig = Field(default_factory=TransportConfig)
    clock_offset_seconds: float = 0.0
    firmware_version: str = "0.9.0-demo"
    controller_version: str = "0.1.0"

    @field_validator("poll_interval_seconds")
    @classmethod
    def _poll_interval_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("poll_interval_seconds must be > 0")
        return value

    @field_validator("gateway_id", "gateway_code", "tenant_id", "asset_code", "config_version")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    def resolved_db_path(self) -> str:
        return self.buffer.db_path.format(gateway_id=self.gateway_id)

    def resolved_topic(self) -> str:
        return self.transport.topic_template.format(
            tenant_id=self.tenant_id, gateway_id=self.gateway_id
        )
