"""Ground-truth leakage prevention (Phase 12 brief §1, §35): the estimator's only inputs
are Phase 10 feature vectors and its own prior output — never simulator hidden state.
Mirrors `ml-service`'s `datasets.leakage_audit` approach for Phase 11: a structural,
automated proof, not a one-time manual review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.features.definitions.sets import FEATURE_SETS
from app.state_estimation.config.policy import load_state_estimation_config

_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "app" / "state_estimation"

#: Simulator hidden-state/ground-truth field names that must never appear as an estimator
#: input feature name (Phase 12 brief §1's explicit list, plus the ground-truth-record
#: field names discovered in `simulator/simulator/engine/output.py`).
_FORBIDDEN_TOKENS = (
    "restriction_factor",
    "leakage_factor",
    "pump_efficiency",
    "bearing_health",
    "lubrication_effectiveness",
    "scenario_type",
    "scenario_phase",
    "lifecycle_state",
    "severity",
    "ground_truth",
    "true_value",
)


def _all_source_files() -> list[Path]:
    return sorted(_PACKAGE_ROOT.rglob("*.py"))


def test_state_estimation_package_never_imports_simulator() -> None:
    for path in _all_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                assert name is not None
                assert not name.startswith("simulator"), (
                    f"{path} imports {name!r} — app.state_estimation must never import "
                    "the simulator package (Phase 12 brief §1)"
                )


def test_state_estimation_package_never_imports_ml_service() -> None:
    """Not a leakage risk per se, but a boundary-cleanliness check: ground-truth-adjacent
    dataset-building code (`ml_service.datasets.ground_truth`) has no business being a
    dependency of the online/replay estimator."""
    for path in _all_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                assert name is not None
                assert not name.startswith("ml_service"), (
                    f"{path} imports {name!r} — app.state_estimation must not depend on "
                    "ml_service"
                )


@pytest.mark.parametrize("state_type", ["LUBRICATION_DELIVERY_STATE", "BEARING_CONDITION_STATE"])
def test_configured_channels_are_real_phase10_state_estimation_features(state_type: str) -> None:
    config = load_state_estimation_config()
    catalog_names = set(FEATURE_SETS["STATE_ESTIMATION_V1"].feature_names)
    for channel in config.states[state_type].channels:
        assert (
            channel.feature_name in catalog_names
        ), f"{channel.feature_name!r} is not a real Phase 10 STATE_ESTIMATION_V1 feature"


def test_configured_channel_names_contain_no_forbidden_ground_truth_token() -> None:
    config = load_state_estimation_config()
    for state_config in config.states.values():
        for channel in state_config.channels:
            lowered = channel.feature_name.lower()
            for token in _FORBIDDEN_TOKENS:
                assert (
                    token not in lowered
                ), f"{channel.feature_name!r} contains forbidden token {token!r}"


def test_no_phase10_state_estimation_feature_name_is_a_forbidden_token() -> None:
    """Defense in depth: even features NOT currently configured as channels are checked,
    so a future config edit adding a new channel can't silently introduce a leak."""
    for name in FEATURE_SETS["STATE_ESTIMATION_V1"].feature_names:
        lowered = name.lower()
        for token in _FORBIDDEN_TOKENS:
            assert token not in lowered, f"{name!r} contains forbidden token {token!r}"
