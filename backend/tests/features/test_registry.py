"""Feature registry and feature-set contract tests."""

from pathlib import Path

from app.features.definitions import FEATURE_DEFINITIONS, FEATURE_REGISTRY, FEATURE_SETS
from app.features.definitions.render_catalog import render_feature_catalog


def test_registry_definitions_are_unique_versioned_typed_and_documented() -> None:
    assert len(FEATURE_DEFINITIONS) == len(FEATURE_REGISTRY)
    assert len(FEATURE_DEFINITIONS) >= 80
    for definition in FEATURE_DEFINITIONS:
        assert definition.name == definition.name.lower()
        assert definition.version in {"1.0.0", "1.0.1"}
        assert definition.unit
        assert definition.description
        assert definition.quality_requirement
        assert definition.null_behavior == "PRESERVE_MISSING_AND_LIST_IN_MISSING_FEATURES"


def test_required_feature_sets_are_versioned_and_reference_registry() -> None:
    assert set(FEATURE_SETS) == {
        "LUBRICATION_ANOMALY_V1",
        "FAILURE_CLASSIFICATION_V1",
        "REFILL_FORECAST_V1",
        "STATE_ESTIMATION_V1",
    }
    for feature_set in FEATURE_SETS.values():
        assert feature_set.version in {"1.0.1", "1.0.2"}
        assert feature_set.intended_use
        assert feature_set.feature_names
        assert set(feature_set.feature_names) <= set(FEATURE_REGISTRY)
    assert FEATURE_SETS["LUBRICATION_ANOMALY_V1"].version == "1.0.2"
    assert FEATURE_REGISTRY["temporal.current_pressure_deviation_duration"].version == "1.0.1"
    assert FEATURE_REGISTRY["bearing_temp.robust_deviation"].version == "1.0.1"


def test_catalog_covers_every_required_feature_group() -> None:
    groups = {definition.group.value for definition in FEATURE_DEFINITIONS}
    assert groups == {
        "CURRENT_STATE",
        "ROLLING_STATISTICAL",
        "BASELINE_DEVIATION",
        "TREND_RATE",
        "CYCLE",
        "CROSS_SIGNAL",
        "TEMPORAL",
        "QUALITY",
        "CONTEXT",
        "RULE_EVIDENCE",
    }


def test_checked_in_feature_catalog_matches_runtime_registry() -> None:
    catalog_path = Path(__file__).parents[3] / "docs" / "FEATURE_CATALOG.md"
    assert catalog_path.read_text().rstrip() == render_feature_catalog().rstrip()
