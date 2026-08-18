"""Maintainable Phase 10 feature catalog.

Names are stable machine-readable contracts. Adding or changing semantics requires a new
definition version; renaming a feature is a breaking feature-set change.
"""

from __future__ import annotations

from app.features.domain.models import FeatureDataType as T
from app.features.domain.models import FeatureDefinition
from app.features.domain.models import FeatureGroup as G

ALL_SETS = (
    "LUBRICATION_ANOMALY_V1",
    "FAILURE_CLASSIFICATION_V1",
    "REFILL_FORECAST_V1",
    "STATE_ESTIMATION_V1",
)
LUBE_SETS = ("LUBRICATION_ANOMALY_V1", "FAILURE_CLASSIFICATION_V1", "STATE_ESTIMATION_V1")
CONDITION_SETS = ("LUBRICATION_ANOMALY_V1", "FAILURE_CLASSIFICATION_V1")


def _d(
    name: str,
    group: G,
    data_type: T,
    unit: str,
    sources: tuple[str, ...] = (),
    *,
    window: int | None = None,
    aggregation: str,
    description: str,
    sets: tuple[str, ...] = ALL_SETS,
    quality: str = "ELIGIBLE_OR_CAUTION_AND_GOOD_READING",
    context: tuple[str, ...] = (),
    version: str = "1.0.0",
) -> FeatureDefinition:
    return FeatureDefinition(
        name=name,
        version=version,
        group=group,
        data_type=data_type,
        unit=unit,
        entity_scope="MACHINE",
        source_measurements=sources,
        window_seconds=window,
        aggregation=aggregation,
        context_requirements=context,
        quality_requirement=quality,
        null_behavior="PRESERVE_MISSING_AND_LIST_IN_MISSING_FEATURES",
        description=description,
        feature_sets=sets,
    )


_SIGNALS = {
    "pressure": ("PRESSURE", "bar"),
    "flow": ("FLOW", "cm3/min"),
    "pump_current": ("PUMP_CURRENT", "A"),
    "pump_runtime": ("PUMP_RUNTIME", "seconds"),
    "reservoir_level": ("RESERVOIR_LEVEL", "percent"),
    "bearing_temp": ("BEARING_TEMPERATURE", "degC"),
    "vibration_rms": ("VIBRATION_RMS", "mm/s"),
    "vibration_peak": ("VIBRATION_PEAK", "mm/s"),
    "rpm": ("RPM", "rpm"),
    "load": ("LOAD", "percent"),
    "lubricant_temp": ("LUBRICANT_TEMPERATURE", "degC"),
    "cycle_completion": ("CYCLE_COMPLETION", "boolean"),
    "piston_movement": ("PISTON_MOVEMENT", "count"),
}

definitions: list[FeatureDefinition] = []

for stem, (measurement, unit) in _SIGNALS.items():
    current_type = T.BOOLEAN if unit == "boolean" else (T.INTEGER if unit == "count" else T.FLOAT)
    definitions.append(
        _d(
            f"{stem}.current",
            G.CURRENT_STATE,
            current_type,
            unit,
            (measurement,),
            aggregation="latest_event_time_observation",
            description=(
                f"Latest trusted {measurement.lower()} observation at or before as-of time."
            ),
        )
    )
    definitions.append(
        _d(
            f"availability.has_{stem}_sensor",
            G.CONTEXT,
            T.BOOLEAN,
            "dimensionless",
            (measurement,),
            aggregation="registered_sensor_exists",
            description=f"Whether the asset hierarchy has a registered {measurement} sensor.",
            quality="NOT_APPLICABLE",
        )
    )

_ROLLING = {
    "pressure": ("PRESSURE", "bar", 900, ("median", "stddev", "p95", "count")),
    "flow": ("FLOW", "cm3/min", 900, ("median", "stddev", "p05", "count")),
    "pump_current": ("PUMP_CURRENT", "A", 900, ("mean", "stddev", "max")),
    "bearing_temp": ("BEARING_TEMPERATURE", "degC", 3600, ("median", "mad", "p95")),
    "vibration_rms": ("VIBRATION_RMS", "mm/s", 3600, ("median", "mad", "p95")),
    "reservoir_level": ("RESERVOIR_LEVEL", "percent", 21600, ("median", "range")),
    "rpm": ("RPM", "rpm", 900, ("median", "stddev")),
    "load": ("LOAD", "percent", 900, ("median", "stddev")),
}
for stem, (measurement, unit, seconds, stats) in _ROLLING.items():
    label = {900: "15m", 3600: "1h", 21600: "6h"}[seconds]
    for stat in stats:
        definitions.append(
            _d(
                f"{stem}.rolling_{stat}.{label}",
                G.ROLLING_STATISTICAL,
                T.INTEGER if stat == "count" else T.FLOAT,
                "count" if stat == "count" else unit,
                (measurement,),
                window=seconds,
                aggregation=stat,
                description=f"Trusted event-time {stat} for {measurement} over {label}.",
            )
        )

for stem, (measurement, unit) in {
    key: _SIGNALS[key]
    for key in (
        "pressure",
        "flow",
        "pump_current",
        "reservoir_level",
        "bearing_temp",
        "vibration_rms",
    )
}.items():
    for suffix, out_unit, aggregation in (
        ("delta_from_baseline", unit, "latest_minus_active_baseline_median"),
        ("relative_to_baseline", "dimensionless", "latest_divided_by_active_baseline_median"),
        ("robust_deviation", "dimensionless", "absolute_mad_standardized_distance"),
        ("percentage_deviation", "percent", "percentage_delta_from_active_baseline_median"),
    ):
        definitions.append(
            _d(
                f"{stem}.{suffix}",
                G.BASELINE_DEVIATION,
                T.FLOAT,
                out_unit,
                (measurement,),
                aggregation=aggregation,
                context=("operating_state", "cycle_phase"),
                description=(
                    f"Explainable {suffix.replace('_', ' ')} using an ACTIVE baseline only."
                ),
                version="1.0.1",
            )
        )

for stem, measurement, window, label, unit in (
    ("pressure", "PRESSURE", 900, "15m", "bar/min"),
    ("flow", "FLOW", 900, "15m", "cm3/min/min"),
    ("reservoir_level", "RESERVOIR_LEVEL", 21600, "6h", "percent/hour"),
    ("bearing_temp", "BEARING_TEMPERATURE", 3600, "1h", "degC/hour"),
    ("vibration_rms", "VIBRATION_RMS", 3600, "1h", "mm/s/hour"),
):
    definitions.append(
        _d(
            f"{stem}.slope.{label}",
            G.TREND_RATE,
            T.FLOAT,
            unit,
            (measurement,),
            window=window,
            aggregation="robust_pairwise_slope",
            description=f"Robust event-time slope for {measurement} over {label}.",
        )
    )

for stem in ("pressure", "flow", "pump_current", "reservoir_level"):
    measurement, unit = _SIGNALS[stem]
    for suffix, out_unit, agg in (
        ("first_difference", unit, "latest_minus_previous"),
        ("relative_difference", "dimensionless", "latest_minus_previous_over_previous"),
        ("rate_per_minute", f"{unit}/min", "difference_over_event_time_minutes"),
    ):
        definitions.append(
            _d(
                f"{stem}.{suffix}",
                G.TREND_RATE,
                T.FLOAT,
                out_unit,
                (measurement,),
                aggregation=agg,
                description=f"Event-time {suffix.replace('_', ' ')} for {measurement}.",
            )
        )

for name, unit, sources, description in (
    (
        "cycle.pressure_rise_time",
        "seconds",
        ("PRESSURE",),
        "Rise time to 90% of the latest observed cycle peak.",
    ),
    (
        "cycle.peak_pressure",
        "bar",
        ("PRESSURE",),
        "Peak pressure in the latest observed lubrication cycle.",
    ),
    (
        "cycle.mean_delivery_pressure",
        "bar",
        ("PRESSURE",),
        "Mean pressure in the latest observed lubrication cycle.",
    ),
    (
        "cycle.flow_integral",
        "cm3",
        ("FLOW",),
        "Event-time trapezoidal flow integral during the latest cycle.",
    ),
    (
        "cycle.delivered_volume",
        "cm3",
        ("FLOW",),
        "Observed delivered-volume proxy from flow integration.",
    ),
    (
        "cycle.pump_runtime",
        "seconds",
        ("PUMP_RUNTIME", "PUMP_CURRENT"),
        "Observed runtime or current-derived runtime during the latest cycle.",
    ),
    ("cycle.duration", "seconds", ("PRESSURE",), "Duration of the latest observed pressure cycle."),
    ("cycle.success", "boolean", ("CYCLE_COMPLETION",), "Latest observed cycle completion result."),
    (
        "cycle.time_since_last_success",
        "seconds",
        ("CYCLE_COMPLETION",),
        "Time since the latest observed successful cycle.",
    ),
    (
        "cycle.failed_recent.6h",
        "count",
        ("CYCLE_COMPLETION",),
        "Failed observed cycles in the prior six hours.",
    ),
    (
        "cycle.partial_recent.6h",
        "count",
        ("PRESSURE", "CYCLE_COMPLETION"),
        "Incomplete observed pressure cycles in the prior six hours.",
    ),
):
    definitions.append(
        _d(
            name,
            G.CYCLE,
            T.BOOLEAN if unit == "boolean" else (T.INTEGER if unit == "count" else T.FLOAT),
            unit,
            sources,
            window=21600,
            aggregation="observed_cycle_segmentation",
            description=description,
            sets=LUBE_SETS,
        )
    )

for name, unit, sources, description in (
    (
        "cross.pressure_to_flow_ratio",
        "bar/(cm3/min)",
        ("PRESSURE", "FLOW"),
        "Latest trusted pressure divided by flow with a near-zero guard.",
    ),
    (
        "cross.pump_current_to_flow_ratio",
        "A/(cm3/min)",
        ("PUMP_CURRENT", "FLOW"),
        "Latest trusted pump current divided by flow.",
    ),
    (
        "cross.pressure_change_vs_flow_change",
        "dimensionless",
        ("PRESSURE", "FLOW"),
        "Pressure relative change minus flow relative change.",
    ),
    (
        "cross.reservoir_depletion_vs_delivered_volume",
        "percent/cm3",
        ("RESERVOIR_LEVEL", "FLOW"),
        "Observed reservoir depletion relative to integrated delivered volume.",
    ),
    (
        "cross.bearing_temp_vs_load",
        "degC/percent",
        ("BEARING_TEMPERATURE", "LOAD"),
        "Bearing temperature relative to machine load.",
    ),
    (
        "cross.vibration_vs_rpm",
        "(mm/s)/rpm",
        ("VIBRATION_RMS", "RPM"),
        "Vibration RMS relative to rotational speed.",
    ),
    (
        "cross.pump_runtime_vs_delivered_volume",
        "seconds/cm3",
        ("PUMP_RUNTIME", "FLOW"),
        "Pump runtime relative to observed delivered volume.",
    ),
):
    definitions.append(
        _d(
            name,
            G.CROSS_SIGNAL,
            T.FLOAT,
            unit,
            sources,
            aggregation="guarded_ratio_or_relative_change",
            description=description,
            sets=CONDITION_SETS,
        )
    )

for name, sources, description in (
    (
        "temporal.time_since_first_pressure_deviation.24h",
        ("PRESSURE",),
        "Elapsed seconds since the first continuing pressure baseline deviation in 24h.",
    ),
    (
        "temporal.time_since_first_flow_deviation.24h",
        ("FLOW",),
        "Elapsed seconds since the first continuing flow baseline deviation in 24h.",
    ),
    (
        "temporal.current_pressure_deviation_duration",
        ("PRESSURE",),
        "Duration of the current trailing pressure deviation run.",
    ),
    (
        "temporal.consecutive_deviating_cycles",
        ("PRESSURE",),
        "Count of trailing cycles with peak pressure materially deviating from baseline.",
    ),
):
    definitions.append(
        _d(
            name,
            G.TEMPORAL,
            T.FLOAT if "cycles" not in name else T.INTEGER,
            "seconds" if "cycles" not in name else "count",
            sources,
            window=86400,
            aggregation="past_only_deviation_run",
            description=description,
            sets=CONDITION_SETS,
            version="1.0.1",
        )
    )

for name, dtype, unit, window, description in (
    (
        "quality.trusted_fraction.15m",
        T.FLOAT,
        "fraction",
        900,
        "Fraction of rows eligible and individually GOOD in 15m.",
    ),
    (
        "quality.caution_fraction.15m",
        T.FLOAT,
        "fraction",
        900,
        "Fraction of rows from caution-eligible sensors in 15m.",
    ),
    (
        "quality.missing_fraction.15m",
        T.FLOAT,
        "fraction",
        900,
        "Fraction of missing or unavailable observations in 15m.",
    ),
    (
        "quality.late_fraction.15m",
        T.FLOAT,
        "fraction",
        900,
        "Fraction whose edge receipt lag exceeds the configured demo threshold.",
    ),
    (
        "quality.issue_count.1h",
        T.INTEGER,
        "count",
        3600,
        "Quality issues whose event-time evidence intersects the prior hour.",
    ),
    (
        "quality.communication_loss_recent",
        T.BOOLEAN,
        "dimensionless",
        3600,
        "Recent communication-loss evidence indicator.",
    ),
    (
        "quality.sensor_drift_suspected_recent",
        T.BOOLEAN,
        "dimensionless",
        21600,
        "Recent sensor-drift-suspected evidence indicator.",
    ),
):
    definitions.append(
        _d(
            name,
            G.QUALITY,
            dtype,
            unit,
            (),
            window=window,
            aggregation="quality_metadata_summary",
            description=description,
            quality="USES_ALL_ROWS_AS_QUALITY_EVIDENCE",
        )
    )

for name, description in (
    (
        "rules.restriction_pattern_active",
        "An ACTIVE restriction-pattern rule finding exists as of the vector time.",
    ),
    (
        "rules.leakage_pattern_active",
        "An ACTIVE leakage-pattern rule finding exists as of the vector time.",
    ),
    (
        "rules.pump_degradation_pattern_active",
        "An ACTIVE pump-degradation-pattern finding exists as of the vector time.",
    ),
    (
        "rules.bearing_condition_pattern_active",
        "An ACTIVE independent-bearing-condition finding exists as of the vector time.",
    ),
):
    definitions.append(
        _d(
            name,
            G.RULE_EVIDENCE,
            T.BOOLEAN,
            "dimensionless",
            (),
            aggregation="active_rule_finding_indicator",
            description=description,
            sets=CONDITION_SETS,
            quality="RULE_FINDING_OWN_QUALITY_CONTEXT",
        )
    )
definitions.append(
    _d(
        "rules.evidence_strength",
        G.RULE_EVIDENCE,
        T.INTEGER,
        "ordinal",
        (),
        aggregation="maximum_active_strength_low_1_moderate_2_strong_3",
        description="Maximum evidence strength across ACTIVE findings; not a probability.",
        sets=CONDITION_SETS,
        quality="RULE_FINDING_OWN_QUALITY_CONTEXT",
    )
)

for name, dtype, description in (
    ("context.machine_type", T.STRING, "Explicit machine-type category."),
    ("context.criticality", T.STRING, "Explicit machine criticality category."),
    ("context.operating_state", T.STRING, "Latest observed operating-state category."),
    ("context.load_bucket", T.STRING, "Explicit LOW/NORMAL/HIGH/UNKNOWN load bucket."),
    ("context.rpm_bucket", T.STRING, "Explicit STOPPED/LOW/NOMINAL/HIGH/UNKNOWN RPM bucket."),
    ("context.cycle_phase", T.STRING, "Observable ACTIVE/IDLE cycle phase derived from pressure."),
    (
        "context.sensor_availability_mask",
        T.STRING,
        "Stable comma-separated registered measurement-type mask.",
    ),
    ("context.firmware_version", T.STRING, "Latest observed sensor firmware version."),
    ("context.controller_version", T.STRING, "Latest observed controller/config version."),
):
    definitions.append(
        _d(
            name,
            G.CONTEXT,
            dtype,
            "category",
            (),
            aggregation="explicit_category",
            description=description,
            quality="NOT_APPLICABLE",
        )
    )

FEATURE_DEFINITIONS = tuple(definitions)
FEATURE_REGISTRY = {definition.name: definition for definition in FEATURE_DEFINITIONS}

if len(FEATURE_REGISTRY) != len(FEATURE_DEFINITIONS):
    raise RuntimeError("Feature catalog contains duplicate names")
