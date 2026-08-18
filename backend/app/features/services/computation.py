"""Shared point-in-time feature computation used by online and historical paths."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from app.baselines.domain.statistics import compute_robust_statistics
from app.features.config.policy import FeaturePolicy
from app.features.definitions.catalog import FEATURE_REGISTRY
from app.features.definitions.sets import FEATURE_SETS
from app.features.domain.context import BaselineSnapshot, FeatureContext, TelemetryPoint
from app.features.domain.models import FeatureValue

_GOOD = "GOOD"
_ELIGIBLE = {"ELIGIBLE", "ELIGIBLE_WITH_CAUTION"}
_EPSILON_MISSING = "Denominator is missing or within the configured near-zero guard."


class _Builder:
    def __init__(self, feature_set: str) -> None:
        self.definition = FEATURE_SETS[feature_set]
        self.allowed = set(self.definition.feature_names)
        self.values: dict[str, FeatureValue] = {}

    def set(self, name: str, value: FeatureValue | None) -> None:
        if name not in self.allowed or value is None:
            return
        if isinstance(value, float) and not math.isfinite(value):
            return
        self.values[name] = value

    def missing(self) -> tuple[str, ...]:
        return tuple(sorted(self.allowed - self.values.keys()))


def _trusted(point: TelemetryPoint) -> bool:
    return point.eligibility in _ELIGIBLE and point.quality == _GOOD and point.value is not None


def _window(points: list[TelemetryPoint], as_of: datetime, seconds: int) -> list[TelemetryPoint]:
    start = as_of - timedelta(seconds=seconds)
    return [p for p in points if start <= p.source_timestamp <= as_of]


def _latest_point(points: list[TelemetryPoint]) -> TelemetryPoint | None:
    if not points:
        return None
    return max(
        points,
        key=lambda point: (
            point.source_timestamp,
            float(point.value) if point.value is not None else -math.inf,
            str(point.sensor_id),
            str(point.event_id),
        ),
    )


def _robust_slope(
    points: list[TelemetryPoint], *, seconds_per_unit: float, max_points: int
) -> float | None:
    ordered = sorted((p for p in points if p.value is not None), key=lambda p: p.source_timestamp)
    if len(ordered) < 2:
        return None
    if len(ordered) > max_points:
        indexes = {round(i * (len(ordered) - 1) / (max_points - 1)) for i in range(max_points)}
        ordered = [ordered[i] for i in sorted(indexes)]
    slopes: list[float] = []
    for index, left in enumerate(ordered[:-1]):
        for right in ordered[index + 1 :]:
            delta_seconds = (right.source_timestamp - left.source_timestamp).total_seconds()
            if delta_seconds > 0 and left.value is not None and right.value is not None:
                slopes.append((right.value - left.value) / delta_seconds * seconds_per_unit)
    return statistics.median(slopes) if slopes else None


def _safe_ratio(numerator: float | None, denominator: float | None, epsilon: float) -> float | None:
    if numerator is None or denominator is None or abs(denominator) <= epsilon:
        return None
    return numerator / denominator


def _select_baseline(
    baselines: list[BaselineSnapshot],
    measurement: str,
    sensor_id: object,
    operating_state: str | None,
    cycle_phase: str | None,
) -> BaselineSnapshot | None:
    candidates = [
        b
        for b in baselines
        if b.measurement_type == measurement
        and b.sensor_id == sensor_id
        and b.metric_kind == "STANDARD"
    ]

    def score(item: BaselineSnapshot) -> tuple[int, int, str]:
        context = item.context
        exact = bool(context) and (
            context.get("operating_state") in (None, operating_state)
            and context.get("cycle_phase") in (None, cycle_phase)
        )
        strategy_score = {
            "CONTEXTUAL_ASSET_BASELINE": 3 if exact else 0,
            "ROLLING_ASSET_BASELINE": 2,
            "STATIC_ENGINEERING_REFERENCE": 1,
        }.get(item.strategy, 0)
        return strategy_score, item.version, str(item.profile_id)

    candidates = [candidate for candidate in candidates if score(candidate)[0] > 0]
    return max(candidates, key=score) if candidates else None


def _segments(points: list[TelemetryPoint], threshold: float) -> list[list[TelemetryPoint]]:
    ordered = sorted(points, key=lambda p: p.source_timestamp)
    segments: list[list[TelemetryPoint]] = []
    current: list[TelemetryPoint] = []
    for point in ordered:
        if point.value is not None and point.value > threshold:
            current.append(point)
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return [segment for segment in segments if len(segment) >= 2]


def _integral_by_sensor(
    points: list[TelemetryPoint], start: datetime, end: datetime
) -> float | None:
    by_sensor: dict[object, list[TelemetryPoint]] = defaultdict(list)
    for point in points:
        if start <= point.source_timestamp <= end and point.value is not None:
            by_sensor[point.sensor_id].append(point)
    total = 0.0
    intervals = 0
    for sensor_points in by_sensor.values():
        ordered = sorted(sensor_points, key=lambda p: p.source_timestamp)
        for left, right in zip(ordered, ordered[1:], strict=False):
            minutes = (right.source_timestamp - left.source_timestamp).total_seconds() / 60.0
            if minutes > 0 and left.value is not None and right.value is not None:
                total += (left.value + right.value) / 2.0 * minutes
                intervals += 1
    return total if intervals else None


def _relative_change(
    points: list[TelemetryPoint], epsilon: float
) -> tuple[float | None, float | None, float | None]:
    ordered = sorted(
        (p for p in points if p.value is not None),
        key=lambda p: (p.source_timestamp, str(p.sensor_id)),
    )
    if len(ordered) < 2:
        return None, None, None
    previous, latest = ordered[-2], ordered[-1]
    assert previous.value is not None and latest.value is not None
    difference = latest.value - previous.value
    relative = _safe_ratio(difference, previous.value, epsilon)
    minutes = (latest.source_timestamp - previous.source_timestamp).total_seconds() / 60.0
    rate = difference / minutes if minutes > 0 else None
    return difference, relative, rate


def compute_feature_values(
    context: FeatureContext, feature_set: str, policy: FeaturePolicy
) -> tuple[
    dict[str, FeatureValue],
    tuple[str, ...],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, int | float],
]:
    """Compute one deterministic vector using only points with source time <= as-of."""
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"Unknown feature set: {feature_set}")
    if any(point.source_timestamp > context.as_of_timestamp for point in context.points):
        raise ValueError("FeatureContext contains future telemetry")

    builder = _Builder(feature_set)
    by_measurement: dict[str, list[TelemetryPoint]] = defaultdict(list)
    all_by_measurement: dict[str, list[TelemetryPoint]] = defaultdict(list)
    for point in context.points:
        all_by_measurement[point.measurement_type].append(point)
        if _trusted(point):
            by_measurement[point.measurement_type].append(point)

    measurement_by_stem = {
        "pressure": "PRESSURE",
        "flow": "FLOW",
        "pump_current": "PUMP_CURRENT",
        "pump_runtime": "PUMP_RUNTIME",
        "reservoir_level": "RESERVOIR_LEVEL",
        "bearing_temp": "BEARING_TEMPERATURE",
        "vibration_rms": "VIBRATION_RMS",
        "vibration_peak": "VIBRATION_PEAK",
        "rpm": "RPM",
        "load": "LOAD",
        "lubricant_temp": "LUBRICANT_TEMPERATURE",
        "cycle_completion": "CYCLE_COMPLETION",
        "piston_movement": "PISTON_MOVEMENT",
    }
    registered = {sensor.measurement_type for sensor in context.sensors}
    latest_values: dict[str, float | None] = {}
    latest_points: dict[str, TelemetryPoint | None] = {}
    for stem, measurement in measurement_by_stem.items():
        current_point = _latest_point(by_measurement[measurement])
        value = current_point.value if current_point is not None else None
        latest_points[stem] = current_point
        latest_values[stem] = value
        builder.set(f"{stem}.current", value)
        builder.set(f"availability.has_{stem}_sensor", measurement in registered)

    rolling = {
        "pressure": ("PRESSURE", 900, "15m", ("median", "stddev", "p95", "count")),
        "flow": ("FLOW", 900, "15m", ("median", "stddev", "p05", "count")),
        "pump_current": ("PUMP_CURRENT", 900, "15m", ("mean", "stddev", "max")),
        "bearing_temp": ("BEARING_TEMPERATURE", 3600, "1h", ("median", "mad", "p95")),
        "vibration_rms": ("VIBRATION_RMS", 3600, "1h", ("median", "mad", "p95")),
        "reservoir_level": ("RESERVOIR_LEVEL", 21600, "6h", ("median", "range")),
        "rpm": ("RPM", 900, "15m", ("median", "stddev")),
        "load": ("LOAD", 900, "15m", ("median", "stddev")),
    }
    for stem, (measurement, seconds, label, stat_names) in rolling.items():
        points = _window(by_measurement[measurement], context.as_of_timestamp, seconds)
        values = [p.value for p in points if p.value is not None]
        stats = compute_robust_statistics(values)
        if stats is None:
            continue
        data = stats.to_dict()
        data["range"] = stats.max - stats.min
        for stat_name in stat_names:
            builder.set(f"{stem}.rolling_{stat_name}.{label}", data[stat_name])

    operating_state = None
    all_trusted = [p for points in by_measurement.values() for p in points]
    if all_trusted:
        operating_state = max(all_trusted, key=lambda p: p.source_timestamp).operating_state
    cycle_phase = (
        "ACTIVE"
        if (latest_values["pressure"] or 0.0) > policy.pressure_cycle_idle_threshold
        else "IDLE"
    )

    baseline_versions: dict[str, object] = {}
    selected_baselines: dict[str, BaselineSnapshot] = {}
    for stem in (
        "pressure",
        "flow",
        "pump_current",
        "reservoir_level",
        "bearing_temp",
        "vibration_rms",
    ):
        measurement = measurement_by_stem[stem]
        latest_point_for_signal = latest_points[stem]
        if latest_point_for_signal is None:
            continue
        baseline = _select_baseline(
            list(context.baselines),
            measurement,
            latest_point_for_signal.sensor_id,
            operating_state,
            cycle_phase,
        )
        observed = latest_values[stem]
        if baseline is None or observed is None:
            continue
        selected_baselines[measurement] = baseline
        median_raw = baseline.statistics.get("median")
        mad_raw = baseline.statistics.get("mad")
        if not isinstance(median_raw, int | float):
            continue
        median = float(median_raw)
        delta = observed - median
        builder.set(f"{stem}.delta_from_baseline", delta)
        builder.set(
            f"{stem}.relative_to_baseline",
            _safe_ratio(observed, median, policy.denominator_epsilon),
        )
        builder.set(
            f"{stem}.percentage_deviation",
            (_safe_ratio(delta, median, policy.denominator_epsilon) or 0.0) * 100.0
            if abs(median) > policy.denominator_epsilon
            else None,
        )
        if isinstance(mad_raw, int | float) and float(mad_raw) > policy.denominator_epsilon:
            builder.set(f"{stem}.robust_deviation", abs(delta) / float(mad_raw))
        baseline_versions[measurement] = {
            "profile_id": str(baseline.profile_id),
            "sensor_id": str(baseline.sensor_id),
            "version": baseline.version,
            "config_version": baseline.config_version,
            "fallback_source": baseline.source_kind,
        }

    for stem, measurement, seconds, unit_seconds, label in (
        ("pressure", "PRESSURE", 900, 60.0, "15m"),
        ("flow", "FLOW", 900, 60.0, "15m"),
        ("reservoir_level", "RESERVOIR_LEVEL", 21600, 3600.0, "6h"),
        ("bearing_temp", "BEARING_TEMPERATURE", 3600, 3600.0, "1h"),
        ("vibration_rms", "VIBRATION_RMS", 3600, 3600.0, "1h"),
    ):
        builder.set(
            f"{stem}.slope.{label}",
            _robust_slope(
                _window(by_measurement[measurement], context.as_of_timestamp, seconds),
                seconds_per_unit=unit_seconds,
                max_points=policy.slope_max_points,
            ),
        )

    relative_changes: dict[str, float | None] = {}
    for stem in ("pressure", "flow", "pump_current", "reservoir_level"):
        difference, relative, rate = _relative_change(
            by_measurement[measurement_by_stem[stem]], policy.denominator_epsilon
        )
        builder.set(f"{stem}.first_difference", difference)
        builder.set(f"{stem}.relative_difference", relative)
        builder.set(f"{stem}.rate_per_minute", rate)
        relative_changes[stem] = relative

    pressure_6h = _window(by_measurement["PRESSURE"], context.as_of_timestamp, 21600)
    cycles = _segments(pressure_6h, policy.pressure_cycle_idle_threshold)
    latest_cycle = cycles[-1] if cycles else None
    delivered_volume: float | None = None
    pump_runtime: float | None = None
    if latest_cycle:
        start, end = latest_cycle[0].source_timestamp, latest_cycle[-1].source_timestamp
        values = [p.value for p in latest_cycle if p.value is not None]
        peak = max(values) if values else None
        builder.set("cycle.peak_pressure", peak)
        builder.set("cycle.mean_delivery_pressure", statistics.fmean(values) if values else None)
        builder.set("cycle.duration", (end - start).total_seconds())
        if peak is not None:
            target = peak * 0.9
            rise = next(
                (p for p in latest_cycle if p.value is not None and p.value >= target), None
            )
            builder.set(
                "cycle.pressure_rise_time",
                (rise.source_timestamp - start).total_seconds() if rise else None,
            )
        delivered_volume = _integral_by_sensor(by_measurement["FLOW"], start, end)
        builder.set("cycle.flow_integral", delivered_volume)
        builder.set("cycle.delivered_volume", delivered_volume)
        runtime_points = [
            p
            for p in by_measurement["PUMP_RUNTIME"]
            if start <= p.source_timestamp <= end and p.value is not None
        ]
        if len(runtime_points) >= 2:
            ordered_runtime = sorted(runtime_points, key=lambda p: p.source_timestamp)
            pump_runtime = max(
                0.0, float(ordered_runtime[-1].value or 0) - float(ordered_runtime[0].value or 0)
            )
        elif _window(
            by_measurement["PUMP_CURRENT"], end, max(1, int((end - start).total_seconds()))
        ):
            pump_runtime = (end - start).total_seconds()
        builder.set("cycle.pump_runtime", pump_runtime)

    completion_6h = _window(by_measurement["CYCLE_COMPLETION"], context.as_of_timestamp, 21600)
    if completion_6h:
        latest_completion = max(completion_6h, key=lambda p: p.source_timestamp)
        success = bool((latest_completion.value or 0.0) >= 0.5)
        builder.set("cycle.success", success)
        successful = [p for p in completion_6h if (p.value or 0.0) >= 0.5]
        builder.set(
            "cycle.time_since_last_success",
            (
                context.as_of_timestamp
                - max(successful, key=lambda p: p.source_timestamp).source_timestamp
            ).total_seconds()
            if successful
            else None,
        )
        builder.set(
            "cycle.failed_recent.6h", sum(1 for p in completion_6h if (p.value or 0.0) < 0.5)
        )
        partial = sum(
            1
            for segment in cycles
            if not any(
                abs((c.source_timestamp - segment[-1].source_timestamp).total_seconds()) <= 60
                and (c.value or 0) >= 0.5
                for c in completion_6h
            )
        )
        builder.set("cycle.partial_recent.6h", partial)

    pressure = latest_values["pressure"]
    flow = latest_values["flow"]
    pump_current = latest_values["pump_current"]
    bearing_temp = latest_values["bearing_temp"]
    vibration = latest_values["vibration_rms"]
    rpm = latest_values["rpm"]
    load = latest_values["load"]
    builder.set(
        "cross.pressure_to_flow_ratio", _safe_ratio(pressure, flow, policy.denominator_epsilon)
    )
    builder.set(
        "cross.pump_current_to_flow_ratio",
        _safe_ratio(pump_current, flow, policy.denominator_epsilon),
    )
    if relative_changes["pressure"] is not None and relative_changes["flow"] is not None:
        builder.set(
            "cross.pressure_change_vs_flow_change",
            relative_changes["pressure"] - relative_changes["flow"],
        )
    reservoir_points = _window(by_measurement["RESERVOIR_LEVEL"], context.as_of_timestamp, 21600)
    if reservoir_points and delivered_volume is not None:
        values = [p.value for p in reservoir_points if p.value is not None]
        depletion = max(values) - min(values) if values else None
        builder.set(
            "cross.reservoir_depletion_vs_delivered_volume",
            _safe_ratio(depletion, delivered_volume, policy.denominator_epsilon),
        )
    builder.set(
        "cross.bearing_temp_vs_load", _safe_ratio(bearing_temp, load, policy.denominator_epsilon)
    )
    builder.set("cross.vibration_vs_rpm", _safe_ratio(vibration, rpm, policy.denominator_epsilon))
    builder.set(
        "cross.pump_runtime_vs_delivered_volume",
        _safe_ratio(pump_runtime, delivered_volume, policy.denominator_epsilon),
    )

    for stem, measurement in (("pressure", "PRESSURE"), ("flow", "FLOW")):
        baseline = selected_baselines.get(measurement)
        if baseline is None:
            continue
        temporal_median = baseline.statistics.get("median")
        temporal_mad = baseline.statistics.get("mad")
        if (
            not isinstance(temporal_median, int | float)
            or not isinstance(temporal_mad, int | float)
            or float(temporal_mad) <= policy.denominator_epsilon
        ):
            continue
        candidates = sorted(
            _window(by_measurement[measurement], context.as_of_timestamp, 86400),
            key=lambda point: (point.source_timestamp, str(point.sensor_id)),
        )
        deviating = [
            abs(float(p.value) - float(temporal_median)) / float(temporal_mad)
            > policy.deviation_mad_multiplier
            for p in candidates
            if p.value is not None
        ]
        ordered = [p for p in candidates if p.value is not None]
        if deviating and any(deviating):
            first = next(index for index, flag in enumerate(deviating) if flag)
            builder.set(
                f"temporal.time_since_first_{stem}_deviation.24h",
                (context.as_of_timestamp - ordered[first].source_timestamp).total_seconds(),
            )
        if stem == "pressure" and deviating and deviating[-1]:
            trailing = 0
            for flag in reversed(deviating):
                if not flag:
                    break
                trailing += 1
            start_point = ordered[len(ordered) - trailing]
            builder.set(
                "temporal.current_pressure_deviation_duration",
                (context.as_of_timestamp - start_point.source_timestamp).total_seconds(),
            )
    pressure_baseline = selected_baselines.get("PRESSURE")
    if pressure_baseline is not None:
        cycle_median = pressure_baseline.statistics.get("median")
        cycle_mad = pressure_baseline.statistics.get("mad")
        if (
            isinstance(cycle_median, int | float)
            and isinstance(cycle_mad, int | float)
            and float(cycle_mad) > policy.denominator_epsilon
        ):
            trailing_cycles = 0
            for segment in reversed(cycles):
                peak = max(float(p.value) for p in segment if p.value is not None)
                if (
                    abs(peak - float(cycle_median)) / float(cycle_mad)
                    <= policy.deviation_mad_multiplier
                ):
                    break
                trailing_cycles += 1
            builder.set("temporal.consecutive_deviating_cycles", trailing_cycles)

    last_15m = _window(
        [p for points in all_by_measurement.values() for p in points], context.as_of_timestamp, 900
    )
    total = len(last_15m)
    if total:
        builder.set(
            "quality.trusted_fraction.15m",
            sum(
                1
                for p in last_15m
                if p.eligibility == "ELIGIBLE" and p.quality == _GOOD and p.value is not None
            )
            / total,
        )
        builder.set(
            "quality.caution_fraction.15m",
            sum(1 for p in last_15m if p.eligibility == "ELIGIBLE_WITH_CAUTION") / total,
        )
        builder.set(
            "quality.missing_fraction.15m",
            sum(
                1
                for p in last_15m
                if p.value is None or p.quality in {"MISSING", "COMMUNICATION_LOSS", "UNAVAILABLE"}
            )
            / total,
        )
        builder.set(
            "quality.late_fraction.15m",
            sum(
                1
                for p in last_15m
                if (p.edge_received_timestamp - p.source_timestamp).total_seconds()
                > policy.late_arrival_seconds
            )
            / total,
        )
    issue_1h = [
        issue
        for issue in context.quality_issues
        if issue.evidence_timestamp >= context.as_of_timestamp - timedelta(hours=1)
    ]
    builder.set("quality.issue_count.1h", len(issue_1h))
    builder.set(
        "quality.communication_loss_recent",
        any(issue.issue_type == "COMMUNICATION_LOSS" for issue in issue_1h),
    )
    builder.set(
        "quality.sensor_drift_suspected_recent",
        any(
            issue.issue_type == "SENSOR_DRIFT_SUSPECTED"
            and issue.evidence_timestamp >= context.as_of_timestamp - timedelta(hours=6)
            for issue in context.quality_issues
        ),
    )

    rule_map = {
        "FLOW_PRESSURE_RESTRICTION_PATTERN": "rules.restriction_pattern_active",
        "FLOW_PRESSURE_LEAKAGE_PATTERN": "rules.leakage_pattern_active",
        "PUMP_DEGRADATION_PATTERN": "rules.pump_degradation_pattern_active",
        "INDEPENDENT_BEARING_CONDITION_PATTERN": "rules.bearing_condition_pattern_active",
    }
    active_types = {rule.finding_type for rule in context.rules}
    for finding_type, feature_name in rule_map.items():
        builder.set(feature_name, finding_type in active_types)
    strength_order = {"LOW": 1, "MODERATE": 2, "STRONG": 3}
    builder.set(
        "rules.evidence_strength",
        max((strength_order.get(rule.evidence_strength, 0) for rule in context.rules), default=0),
    )

    builder.set("context.machine_type", context.machine_type)
    builder.set("context.criticality", context.criticality)
    builder.set("context.operating_state", operating_state)
    builder.set(
        "context.load_bucket",
        "UNKNOWN"
        if load is None
        else (
            "LOW"
            if load < policy.load_low_upper_percent
            else "NORMAL"
            if load < policy.load_normal_upper_percent
            else "HIGH"
        ),
    )
    builder.set(
        "context.rpm_bucket",
        "UNKNOWN"
        if rpm is None
        else (
            "STOPPED"
            if rpm <= policy.rpm_stopped_upper
            else "LOW"
            if rpm < policy.rpm_low_upper
            else "NOMINAL"
            if rpm < policy.rpm_nominal_upper
            else "HIGH"
        ),
    )
    builder.set("context.cycle_phase", cycle_phase)
    builder.set("context.sensor_availability_mask", ",".join(sorted(registered)))
    latest_point = max(all_trusted, key=lambda p: p.source_timestamp) if all_trusted else None
    builder.set("context.firmware_version", latest_point.firmware_version if latest_point else None)
    builder.set(
        "context.controller_version", latest_point.controller_version if latest_point else None
    )

    rule_versions: dict[str, object] = {
        rule.rule_id: rule.rule_version
        for rule in sorted(context.rules, key=lambda r: (r.rule_id, r.rule_version))
    }
    suppressed_point_count = sum(
        1 for points in all_by_measurement.values() for point in points if not _trusted(point)
    )
    quality_summary: dict[str, object] = {
        "state": "NO_TRUSTED_DATA"
        if not all_trusted
        else (
            "CAUTION"
            if any(p.eligibility == "ELIGIBLE_WITH_CAUTION" for p in all_trusted)
            else "TRUSTED"
        ),
        "registered_sensor_count": len(context.sensors),
        "trusted_point_count": len(all_trusted),
        "suppressed_point_count": suppressed_point_count,
        "denominator_guard": _EPSILON_MISSING,
    }
    metrics: dict[str, int | float] = {
        "telemetry_rows_scanned": context.telemetry_rows_scanned,
        "features_generated": len(builder.values),
        "features_missing": len(builder.missing()),
        "features_suppressed_quality": suppressed_point_count,
    }
    return (
        builder.values,
        builder.missing(),
        quality_summary,
        baseline_versions,
        rule_versions,
        metrics,
    )


def definition_versions(feature_set: str) -> dict[str, str]:
    return {
        name: FEATURE_REGISTRY[name].version for name in FEATURE_SETS[feature_set].feature_names
    }
