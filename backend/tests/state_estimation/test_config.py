"""`StateEstimationConfig` fail-fast validation (mirrors `tests/rules_engine` config
tests) and a load of the real shipped `state_estimation_v1.yaml`."""

from __future__ import annotations

import copy
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from app.state_estimation.config.policy import (
    DEFAULT_POLICY_PATH,
    StateEstimationConfig,
    load_state_estimation_config,
)


def _base_raw() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(DEFAULT_POLICY_PATH.read_text())
    return raw


def test_load_real_shipped_config() -> None:
    config = load_state_estimation_config()
    assert config.feature_set == "STATE_ESTIMATION_V1"
    assert set(config.states) == {"LUBRICATION_DELIVERY_STATE", "BEARING_CONDITION_STATE"}
    for state_config in config.states.values():
        assert len(state_config.channels) >= 1


def test_unknown_state_type_rejected() -> None:
    raw = _base_raw()
    raw["states"]["NOT_A_REAL_STATE"] = copy.deepcopy(raw["states"]["LUBRICATION_DELIVERY_STATE"])
    with pytest.raises(ValidationError, match="unknown state type"):
        StateEstimationConfig.model_validate(raw)


def test_empty_channels_rejected() -> None:
    raw = _base_raw()
    raw["states"]["LUBRICATION_DELIVERY_STATE"]["channels"] = []
    with pytest.raises(ValidationError, match="at least one observation channel"):
        StateEstimationConfig.model_validate(raw)


def test_trend_threshold_must_be_below_rate_bound() -> None:
    raw = _base_raw()
    raw["states"]["LUBRICATION_DELIVERY_STATE"]["trend_rate_threshold"] = 1.0
    raw["states"]["LUBRICATION_DELIVERY_STATE"]["rate_bound"] = 0.01
    with pytest.raises(ValidationError, match="trend_rate_threshold must be"):
        StateEstimationConfig.model_validate(raw)


def test_uncertainty_thresholds_must_be_ordered() -> None:
    raw = _base_raw()
    raw["uncertainty"]["low_max_variance"] = 0.5
    raw["uncertainty"]["moderate_max_variance"] = 0.1
    with pytest.raises(ValidationError, match="low_max_variance"):
        StateEstimationConfig.model_validate(raw)


def test_gap_ordering_must_be_valid() -> None:
    raw = _base_raw()
    raw["gap"]["min_dt_seconds"] = 100.0
    raw["gap"]["max_dt_seconds"] = 10.0
    with pytest.raises(ValidationError, match="min_dt_seconds"):
        StateEstimationConfig.model_validate(raw)


def test_caution_inflation_below_one_rejected() -> None:
    raw = _base_raw()
    raw["states"]["LUBRICATION_DELIVERY_STATE"]["caution_inflation_factor"] = 0.5
    with pytest.raises(ValidationError, match="caution_inflation_factor"):
        StateEstimationConfig.model_validate(raw)


def test_extra_unknown_field_rejected() -> None:
    raw = _base_raw()
    raw["not_a_real_field"] = 1
    with pytest.raises(ValidationError):
        StateEstimationConfig.model_validate(raw)
