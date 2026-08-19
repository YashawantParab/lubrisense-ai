from ml_service.domain.labels import FailureLabel, label_for_ground_truth


def test_no_active_scenarios_is_normal() -> None:
    label, source = label_for_ground_truth([])
    assert label == FailureLabel.NORMAL
    assert source is None


def test_scheduled_scenario_is_still_normal() -> None:
    scenarios = [
        {"scenario_type": "GRADUAL_RESTRICTION", "lifecycle_state": "SCHEDULED", "severity": 0.0}
    ]
    label, source = label_for_ground_truth(scenarios)
    assert label == FailureLabel.NORMAL
    assert source is None


def test_developing_restriction_maps_to_restriction() -> None:
    scenarios = [
        {"scenario_type": "GRADUAL_RESTRICTION", "lifecycle_state": "DEVELOPING", "severity": 0.3}
    ]
    label, source = label_for_ground_truth(scenarios)
    assert label == FailureLabel.RESTRICTION
    assert source == "GRADUAL_RESTRICTION"


def test_sensor_drift_and_dropout_both_map_to_sensor_fault() -> None:
    for scenario_type in ("SENSOR_DRIFT", "SENSOR_DROPOUT"):
        scenarios = [{"scenario_type": scenario_type, "lifecycle_state": "SEVERE", "severity": 0.9}]
        label, _ = label_for_ground_truth(scenarios)
        assert label == FailureLabel.SENSOR_FAULT


def test_out_of_schema_scenarios_map_to_unknown() -> None:
    for scenario_type in ("OVER_LUBRICATION", "LOW_RESERVOIR"):
        scenarios = [{"scenario_type": scenario_type, "lifecycle_state": "SEVERE", "severity": 0.9}]
        label, _ = label_for_ground_truth(scenarios)
        assert label == FailureLabel.UNKNOWN


def test_network_failure_only_returns_none_none_dropped_from_supervised() -> None:
    scenarios = [{"scenario_type": "NETWORK_FAILURE", "lifecycle_state": "SEVERE", "severity": 0.9}]
    label, source = label_for_ground_truth(scenarios)
    assert label is None
    assert source is None


def test_multi_fault_picks_highest_severity() -> None:
    scenarios = [
        {"scenario_type": "GRADUAL_RESTRICTION", "lifecycle_state": "DEVELOPING", "severity": 0.2},
        {
            "scenario_type": "INDEPENDENT_BEARING_FAULT",
            "lifecycle_state": "SEVERE",
            "severity": 0.8,
        },
    ]
    label, source = label_for_ground_truth(scenarios)
    assert label == FailureLabel.INDEPENDENT_BEARING_ISSUE
    assert source == "INDEPENDENT_BEARING_FAULT"


def test_multi_fault_with_network_failure_present_ignores_it_but_keeps_other_fault() -> None:
    scenarios = [
        {"scenario_type": "NETWORK_FAILURE", "lifecycle_state": "SEVERE", "severity": 0.95},
        {"scenario_type": "LEAKAGE", "lifecycle_state": "DEVELOPING", "severity": 0.3},
    ]
    label, source = label_for_ground_truth(scenarios)
    assert label == FailureLabel.LEAKAGE
    assert source == "LEAKAGE"
