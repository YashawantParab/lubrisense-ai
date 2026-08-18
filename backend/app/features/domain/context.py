"""Database-free feature input snapshots."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TelemetryPoint:
    event_id: uuid.UUID
    sensor_id: uuid.UUID
    measurement_type: str
    value: float | None
    unit: str
    quality: str
    eligibility: str
    source_timestamp: datetime
    edge_received_timestamp: datetime
    operating_state: str
    firmware_version: str | None
    controller_version: str | None


@dataclass(frozen=True)
class SensorDescriptor:
    sensor_id: uuid.UUID
    measurement_type: str


@dataclass(frozen=True)
class BaselineSnapshot:
    profile_id: uuid.UUID
    sensor_id: uuid.UUID
    measurement_type: str
    strategy: str
    source_kind: str
    version: int
    config_version: str
    metric_kind: str
    context: dict[str, object]
    statistics: dict[str, object]
    window_end: datetime | None


@dataclass(frozen=True)
class RuleSnapshot:
    finding_type: str
    rule_id: str
    rule_version: str
    evidence_strength: str
    first_detected_at: datetime


@dataclass(frozen=True)
class QualityIssueSnapshot:
    issue_type: str
    evidence_timestamp: datetime


@dataclass(frozen=True)
class FeatureContext:
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    machine_type: str
    criticality: str
    as_of_timestamp: datetime
    sensors: tuple[SensorDescriptor, ...]
    points: tuple[TelemetryPoint, ...]
    baselines: tuple[BaselineSnapshot, ...]
    rules: tuple[RuleSnapshot, ...]
    quality_issues: tuple[QualityIssueSnapshot, ...]
    telemetry_rows_scanned: int
