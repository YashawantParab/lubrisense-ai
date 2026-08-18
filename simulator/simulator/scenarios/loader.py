"""Loads `ScenarioDefinition`s from `simulator/config/scenarios/*.yaml` (Phase 4 brief
§19). One file per failure mode — adding/tuning a scenario is a config change, not a code
change.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from simulator.scenarios.definition import ScenarioDefinition

DEFAULT_SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "config" / "scenarios"

#: Bumped whenever any file under `simulator/config/scenarios/` changes in a way that could
#: change existing scenario output — recorded in `RunMetadata.scenario_config_version`
#: (Phase 4 brief §21), analogous to `demo_engineering.yaml`'s `config_version`.
SCENARIO_CONFIG_VERSION = "1"


def list_available_scenarios(directory: Path | None = None) -> list[str]:
    target_dir = directory or DEFAULT_SCENARIOS_DIR
    return sorted(p.stem for p in target_dir.glob("*.yaml"))


def load_scenario_definition(name: str, directory: Path | None = None) -> ScenarioDefinition:
    """`name` is the YAML file's stem, e.g. `"gradual_restriction"` for
    `gradual_restriction.yaml`."""
    target_dir = directory or DEFAULT_SCENARIOS_DIR
    path = target_dir / f"{name}.yaml"
    if not path.exists():
        available = list_available_scenarios(target_dir)
        raise FileNotFoundError(f"No scenario definition {name!r} (available: {available})")
    raw = yaml.safe_load(path.read_text())
    return ScenarioDefinition.model_validate(raw)
