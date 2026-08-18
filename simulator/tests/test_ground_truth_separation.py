from __future__ import annotations

import dataclasses

from simulator.engine.output import GroundTruthRecord, SimulationReading

_HIDDEN_STATE_FIELD_NAMES = {
    "restriction_factor",
    "leakage_factor",
    "pump_efficiency",
    "bearing_health",
    "health",
    "lubrication_effectiveness",
    "sensor_bias",
    "bias",
}


def test_simulation_reading_never_carries_hidden_state_field_names() -> None:
    """Structural proof of Phase 3 brief §18: the observable-telemetry record type must
    never carry a hidden-state field name, so no future adapter can accidentally forward
    ground truth as if it were a sensor reading."""
    reading_fields = {f.name for f in dataclasses.fields(SimulationReading)}
    assert reading_fields.isdisjoint(_HIDDEN_STATE_FIELD_NAMES)


def test_ground_truth_record_is_a_distinct_type_from_simulation_reading() -> None:
    assert GroundTruthRecord is not SimulationReading
    gt_fields = {f.name for f in dataclasses.fields(GroundTruthRecord)}
    assert "pump_efficiency" in gt_fields
    assert "bearings" in gt_fields
    assert "circuits" in gt_fields


def test_simulation_reading_only_exposes_measurement_shaped_fields() -> None:
    reading_fields = {f.name for f in dataclasses.fields(SimulationReading)}
    expected = {
        "simulation_timestamp",
        "tenant_id",
        "asset_id",
        "component_id",
        "sensor_id",
        "measurement_type",
        "true_value",
        "observed_value",
        "unit",
        "quality",
        "operating_state",
        "cycle_id",
        "simulation_state",
    }
    assert reading_fields == expected
