from __future__ import annotations

import pytest
from pydantic import ValidationError

from simulator.scenarios.definition import ProgressionSpec, ScenarioDefinition
from simulator.scenarios.loader import list_available_scenarios, load_scenario_definition
from simulator.scenarios.types import (
    VALID_TARGET_TYPES,
    ProgressionType,
    ScenarioTargetType,
    ScenarioType,
)


def test_mismatched_target_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must target"):
        ScenarioDefinition(
            name="bad",
            scenario_type=ScenarioType.GRADUAL_RESTRICTION,
            target_type=ScenarioTargetType.SENSOR,  # wrong — GRADUAL_RESTRICTION needs CIRCUIT
            description="invalid on purpose",
            progression=ProgressionSpec(type=ProgressionType.LINEAR),
        )


def test_matching_target_type_is_accepted() -> None:
    definition = ScenarioDefinition(
        name="ok",
        scenario_type=ScenarioType.GRADUAL_RESTRICTION,
        target_type=ScenarioTargetType.CIRCUIT,
        description="valid",
        progression=ProgressionSpec(type=ProgressionType.LINEAR),
    )
    assert definition.target_type == ScenarioTargetType.CIRCUIT


def test_every_catalog_scenario_type_has_exactly_one_committed_definition() -> None:
    """Phase 4 brief §5: all 10 injectable catalog failure modes must be implemented."""
    available = list_available_scenarios()
    assert len(available) == 10
    scenario_types_found = {load_scenario_definition(name).scenario_type for name in available}
    assert scenario_types_found == set(ScenarioType)


def test_every_committed_definition_matches_its_valid_target_type() -> None:
    for name in list_available_scenarios():
        definition = load_scenario_definition(name)
        assert definition.target_type == VALID_TARGET_TYPES[definition.scenario_type]


def test_every_committed_definition_declares_demo_disclaimer_in_description_or_docstring() -> None:
    """Not a strict schema field, but every scenario YAML file must carry the file-header
    disclaimer (Phase 4 brief §19) — checked at the raw-file level here."""
    from simulator.scenarios.loader import DEFAULT_SCENARIOS_DIR

    for name in list_available_scenarios():
        text = (DEFAULT_SCENARIOS_DIR / f"{name}.yaml").read_text()
        assert "DEMO SYNTHETIC FAILURE ASSUMPTIONS" in text
        assert "NOT VALIDATED PRODUCTION FAILURE THRESHOLDS" in text


def test_unknown_scenario_name_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_scenario_definition("does_not_exist")


def test_extra_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioDefinition.model_validate(
            {
                "name": "bad",
                "scenario_type": "GRADUAL_RESTRICTION",
                "target_type": "CIRCUIT",
                "description": "x",
                "progression": {"type": "LINEAR"},
                "not_a_real_field": 123,
            }
        )
