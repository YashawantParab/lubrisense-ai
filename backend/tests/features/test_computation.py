"""Pure feature math, missingness, quality gating, and scenario-signature tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.features.config.policy import load_feature_policy
from app.features.domain.context import (
    BaselineSnapshot,
    FeatureContext,
    QualityIssueSnapshot,
    RuleSnapshot,
    SensorDescriptor,
    TelemetryPoint,
)
from app.features.services.computation import compute_feature_values

POLICY = load_feature_policy()


def _point(
    sensor_id: uuid.UUID,
    measurement: str,
    timestamp: datetime,
    value: float | None,
    *,
    eligibility: str = "ELIGIBLE",
    quality: str = "GOOD",
) -> TelemetryPoint:
    return TelemetryPoint(
        event_id=uuid.uuid4(),
        sensor_id=sensor_id,
        measurement_type=measurement,
        value=value,
        unit="unit",
        quality=quality,
        eligibility=eligibility,
        source_timestamp=timestamp,
        edge_received_timestamp=timestamp,
        operating_state="RUNNING_NORMAL_LOAD",
        firmware_version="fw-1",
        controller_version="cfg-1",
    )


def _baseline(
    sensor_id: uuid.UUID, measurement: str, median: float, mad: float
) -> BaselineSnapshot:
    return BaselineSnapshot(
        profile_id=uuid.uuid4(),
        sensor_id=sensor_id,
        measurement_type=measurement,
        strategy="ROLLING_ASSET_BASELINE",
        source_kind="SENSOR_LEVEL",
        version=1,
        config_version="1",
        metric_kind="STANDARD",
        context={},
        statistics={
            "median": median,
            "mad": mad,
            "mean": median,
            "stddev": mad,
            "p05": median - mad,
            "p95": median + mad,
        },
        window_end=None,
    )


def _context(
    as_of: datetime,
    sensors: list[tuple[uuid.UUID, str]],
    points: list[TelemetryPoint],
    baselines: list[BaselineSnapshot] | None = None,
    *,
    rules: list[RuleSnapshot] | None = None,
    quality_issues: list[QualityIssueSnapshot] | None = None,
) -> FeatureContext:
    return FeatureContext(
        tenant_id=uuid.uuid4(),
        machine_id=uuid.uuid4(),
        machine_type="CONVEYOR",
        criticality="HIGH",
        as_of_timestamp=as_of,
        sensors=tuple(
            SensorDescriptor(sensor_id=sid, measurement_type=kind) for sid, kind in sensors
        ),
        points=tuple(points),
        baselines=tuple(baselines or []),
        rules=tuple(rules or []),
        quality_issues=tuple(quality_issues or []),
        telemetry_rows_scanned=len(points),
    )


def test_ineligible_dropout_and_network_values_are_missing_not_zero() -> None:
    now = datetime.now(UTC)
    pressure_id, flow_id, vibration_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    context = _context(
        now,
        [(pressure_id, "PRESSURE"), (flow_id, "FLOW"), (vibration_id, "VIBRATION_RMS")],
        [
            _point(pressure_id, "PRESSURE", now, 12.0),
            _point(flow_id, "FLOW", now, 88.0, eligibility="INELIGIBLE"),
            _point(vibration_id, "VIBRATION_RMS", now, None, quality="MISSING"),
        ],
    )
    values, missing, quality, *_ = compute_feature_values(context, "LUBRICATION_ANOMALY_V1", POLICY)

    assert values["pressure.current"] == 12.0
    assert "flow.current" not in values
    assert "vibration_rms.current" not in values
    assert "flow.current" in missing
    assert values["availability.has_flow_sensor"] is True
    assert values["availability.has_pump_current_sensor"] is False
    assert quality["suppressed_point_count"] == 2
    assert all(value != 0.0 for name, value in values.items() if name.endswith(".current"))


@pytest.mark.parametrize(
    ("quality", "eligibility", "value"),
    [
        pytest.param("GOOD", "INELIGIBLE", 88.0, id="sensor-drift-ineligible"),
        pytest.param("MISSING", "ELIGIBLE", None, id="sensor-dropout"),
        pytest.param("COMMUNICATION_LOSS", "ELIGIBLE", None, id="network-failure"),
    ],
)
def test_sensor_faults_never_contribute_numeric_values(
    quality: str, eligibility: str, value: float | None
) -> None:
    now = datetime.now(UTC)
    sensor_id = uuid.uuid4()
    values, missing, summary, *_ = compute_feature_values(
        _context(
            now,
            [(sensor_id, "FLOW")],
            [
                _point(
                    sensor_id,
                    "FLOW",
                    now,
                    value,
                    eligibility=eligibility,
                    quality=quality,
                )
            ],
        ),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    assert "flow.current" not in values
    assert "flow.current" in missing
    assert values["availability.has_flow_sensor"] is True
    assert summary["suppressed_point_count"] == 1


def test_caution_eligible_good_value_is_included_with_quality_metadata() -> None:
    now = datetime.now(UTC)
    sensor_id = uuid.uuid4()
    values, _missing, summary, *_ = compute_feature_values(
        _context(
            now,
            [(sensor_id, "FLOW")],
            [_point(sensor_id, "FLOW", now, 75.0, eligibility="ELIGIBLE_WITH_CAUTION")],
        ),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    assert values["flow.current"] == 75.0
    assert values["quality.caution_fraction.15m"] == 1.0
    assert summary["state"] == "CAUTION"


def test_same_type_sensor_value_uses_its_own_active_baseline() -> None:
    now = datetime.now(UTC)
    hot_sensor, cool_sensor = uuid.uuid4(), uuid.uuid4()
    values, _missing, _summary, baseline_versions, *_ = compute_feature_values(
        _context(
            now,
            [
                (hot_sensor, "BEARING_TEMPERATURE"),
                (cool_sensor, "BEARING_TEMPERATURE"),
            ],
            [
                _point(cool_sensor, "BEARING_TEMPERATURE", now, 40.0),
                _point(hot_sensor, "BEARING_TEMPERATURE", now, 50.0),
            ],
            [
                _baseline(cool_sensor, "BEARING_TEMPERATURE", 10.0, 1.0),
                _baseline(hot_sensor, "BEARING_TEMPERATURE", 50.0, 1.0),
            ],
        ),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    assert values["bearing_temp.current"] == 50.0
    assert values["bearing_temp.delta_from_baseline"] == 0.0
    assert baseline_versions["BEARING_TEMPERATURE"]["sensor_id"] == str(hot_sensor)  # type: ignore[index]


def test_restriction_leakage_bearing_and_healthy_signatures_are_distinct() -> None:
    now = datetime.now(UTC)
    start = now - timedelta(minutes=14)
    pressure_id, flow_id, current_id, temp_id = (uuid.uuid4() for _ in range(4))
    sensors = [
        (pressure_id, "PRESSURE"),
        (flow_id, "FLOW"),
        (current_id, "PUMP_CURRENT"),
        (temp_id, "BEARING_TEMPERATURE"),
    ]
    baselines = [
        _baseline(pressure_id, "PRESSURE", 10.0, 0.5),
        _baseline(flow_id, "FLOW", 100.0, 5.0),
        _baseline(current_id, "PUMP_CURRENT", 2.0, 0.1),
        _baseline(temp_id, "BEARING_TEMPERATURE", 45.0, 1.0),
    ]

    def signature(pressure_end: float, flow_end: float, temp_end: float) -> dict[str, object]:
        points: list[TelemetryPoint] = []
        for index in range(15):
            timestamp = start + timedelta(minutes=index)
            fraction = index / 14
            points.extend(
                [
                    _point(pressure_id, "PRESSURE", timestamp, 10 + (pressure_end - 10) * fraction),
                    _point(flow_id, "FLOW", timestamp, 100 + (flow_end - 100) * fraction),
                    _point(current_id, "PUMP_CURRENT", timestamp, 2 + fraction),
                    _point(
                        temp_id, "BEARING_TEMPERATURE", timestamp, 45 + (temp_end - 45) * fraction
                    ),
                ]
            )
        values, *_ = compute_feature_values(
            _context(now, sensors, points, baselines), "LUBRICATION_ANOMALY_V1", POLICY
        )
        return values

    restriction = signature(18.0, 55.0, 50.0)
    leakage = signature(9.0, 55.0, 47.0)
    bearing_only = signature(10.0, 100.0, 65.0)
    healthy = signature(10.1, 99.5, 45.2)

    assert restriction["pressure.slope.15m"] > 0
    assert restriction["flow.slope.15m"] < 0
    assert restriction["pressure.delta_from_baseline"] > 0
    assert leakage["pressure.slope.15m"] < restriction["pressure.slope.15m"]
    assert bearing_only["bearing_temp.delta_from_baseline"] > 10
    assert abs(float(bearing_only["pressure.delta_from_baseline"])) < 0.1
    assert abs(float(healthy["pressure.slope.15m"])) < 0.1


def test_temporal_deviation_duration_accumulates_using_past_points_only() -> None:
    now = datetime.now(UTC)
    sensor_id = uuid.uuid4()
    start = now - timedelta(minutes=14)
    points = [
        _point(sensor_id, "PRESSURE", start + timedelta(minutes=index), 10.0 + index * 0.5)
        for index in range(15)
    ]
    baseline = _baseline(sensor_id, "PRESSURE", 10.0, 0.5)
    early_points = points[:9]
    early_as_of = early_points[-1].source_timestamp
    early, *_ = compute_feature_values(
        _context(early_as_of, [(sensor_id, "PRESSURE")], early_points, [baseline]),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    later, *_ = compute_feature_values(
        _context(now, [(sensor_id, "PRESSURE")], points, [baseline]),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    descending, *_ = compute_feature_values(
        _context(now, [(sensor_id, "PRESSURE")], list(reversed(points)), [baseline]),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    assert (
        later["temporal.current_pressure_deviation_duration"]
        > early["temporal.current_pressure_deviation_duration"]
    )
    assert (
        descending["temporal.current_pressure_deviation_duration"]
        == later["temporal.current_pressure_deviation_duration"]
    )


def test_healthy_long_run_remains_stable_around_active_baseline() -> None:
    now = datetime.now(UTC)
    sensor_id = uuid.uuid4()
    points = [
        _point(
            sensor_id,
            "PRESSURE",
            now - timedelta(hours=24) + timedelta(minutes=5 * index),
            10.0 + (0.05 if index % 2 else -0.05),
        )
        for index in range(289)
    ]
    values, *_ = compute_feature_values(
        _context(
            now,
            [(sensor_id, "PRESSURE")],
            points,
            [_baseline(sensor_id, "PRESSURE", 10.0, 0.5)],
        ),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    assert abs(float(values["pressure.delta_from_baseline"])) <= 0.051
    assert abs(float(values["pressure.slope.15m"])) < 0.02
    assert float(values["pressure.robust_deviation"]) <= 0.101


@pytest.mark.parametrize(
    ("instrumentation", "checked", "expected", "absent"),
    [
        pytest.param(
            ("PRESSURE", "FLOW", "PUMP_CURRENT", "BEARING_TEMPERATURE"),
            "availability.has_flow_sensor",
            True,
            "availability.has_vibration_rms_sensor",
            id="full-instrumentation",
        ),
        pytest.param(
            ("PRESSURE", "RESERVOIR_LEVEL"),
            "availability.has_pressure_sensor",
            True,
            "availability.has_flow_sensor",
            id="partial-instrumentation",
        ),
        pytest.param(
            ("BEARING_TEMPERATURE", "VIBRATION_RMS"),
            "availability.has_bearing_temp_sensor",
            True,
            "availability.has_pressure_sensor",
            id="bearing-only",
        ),
        pytest.param(
            (),
            "availability.has_pressure_sensor",
            False,
            "availability.has_flow_sensor",
            id="no-lubrication-telemetry",
        ),
    ],
)
def test_heterogeneous_asset_availability_masks(
    instrumentation: tuple[str, ...], checked: str, expected: bool, absent: str
) -> None:
    now = datetime.now(UTC)
    sensors = [(uuid.uuid4(), measurement) for measurement in instrumentation]
    values, *_ = compute_feature_values(
        _context(now, sensors, []), "LUBRICATION_ANOMALY_V1", POLICY
    )
    assert values[checked] is expected
    assert values[absent] is False


def test_cycle_rate_cross_signal_and_denominator_guards() -> None:
    now = datetime.now(UTC)
    pressure_id, flow_id, current_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    points: list[TelemetryPoint] = []
    for offset, pressure, flow in (
        (0, 0.0, 0.0),
        (10, 2.0, 40.0),
        (20, 6.0, 60.0),
        (30, 10.0, 80.0),
        (40, 10.0, 80.0),
        (50, 0.0, 0.0),
    ):
        timestamp = now - timedelta(seconds=60 - offset)
        points.extend(
            [
                _point(pressure_id, "PRESSURE", timestamp, pressure),
                _point(flow_id, "FLOW", timestamp, flow),
                _point(current_id, "PUMP_CURRENT", timestamp, 2.0 if pressure else 0.0),
            ]
        )
    values, missing, *_ = compute_feature_values(
        _context(
            now,
            [(pressure_id, "PRESSURE"), (flow_id, "FLOW"), (current_id, "PUMP_CURRENT")],
            points,
        ),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    assert values["cycle.pressure_rise_time"] == 20.0
    assert values["cycle.peak_pressure"] == 10.0
    assert values["cycle.delivered_volume"] > 0
    assert "cross.pressure_to_flow_ratio" in missing  # latest observations are both zero


def test_pump_degradation_signature_changes_rise_runtime_current_and_flow() -> None:
    now = datetime.now(UTC)
    pressure_id, flow_id, current_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sensors = [
        (pressure_id, "PRESSURE"),
        (flow_id, "FLOW"),
        (current_id, "PUMP_CURRENT"),
    ]

    def cycle(pressures: tuple[float, ...], flow: float, current: float) -> dict[str, object]:
        points: list[TelemetryPoint] = []
        start = now - timedelta(seconds=10 * (len(pressures) - 1))
        for index, pressure in enumerate(pressures):
            timestamp = start + timedelta(seconds=10 * index)
            points.extend(
                [
                    _point(pressure_id, "PRESSURE", timestamp, pressure),
                    _point(flow_id, "FLOW", timestamp, flow),
                    _point(current_id, "PUMP_CURRENT", timestamp, current),
                ]
            )
        values, *_ = compute_feature_values(
            _context(now, sensors, points), "LUBRICATION_ANOMALY_V1", POLICY
        )
        return values

    healthy = cycle((1.1, 10.0), flow=80.0, current=2.0)
    degraded = cycle((1.1, 2.0, 4.0, 6.0, 10.0), flow=45.0, current=3.5)

    assert degraded["cycle.pressure_rise_time"] > healthy["cycle.pressure_rise_time"]
    assert degraded["cycle.pump_runtime"] > healthy["cycle.pump_runtime"]
    assert degraded["pump_current.current"] > healthy["pump_current.current"]
    assert degraded["flow.current"] < healthy["flow.current"]


def test_rule_evidence_and_quality_issue_features_remain_explicit_evidence() -> None:
    now = datetime.now(UTC)
    values, *_ = compute_feature_values(
        _context(
            now,
            [],
            [],
            rules=[
                RuleSnapshot(
                    finding_type="FLOW_PRESSURE_RESTRICTION_PATTERN",
                    rule_id="restriction-pattern",
                    rule_version="1.2.0",
                    evidence_strength="STRONG",
                    first_detected_at=now - timedelta(minutes=5),
                )
            ],
            quality_issues=[
                QualityIssueSnapshot(
                    issue_type="COMMUNICATION_LOSS",
                    evidence_timestamp=now - timedelta(minutes=10),
                ),
                QualityIssueSnapshot(
                    issue_type="SENSOR_DRIFT_SUSPECTED",
                    evidence_timestamp=now - timedelta(hours=2),
                ),
            ],
        ),
        "LUBRICATION_ANOMALY_V1",
        POLICY,
    )
    assert values["rules.restriction_pattern_active"] is True
    assert values["rules.leakage_pattern_active"] is False
    assert values["rules.evidence_strength"] == 3
    assert values["quality.communication_loss_recent"] is True
    assert values["quality.sensor_drift_suspected_recent"] is True
