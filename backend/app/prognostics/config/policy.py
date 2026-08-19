"""`PrognosticsPolicy` — versioned forecast configuration (Phase 15 brief). Fail-fast, same
convention as every prior phase's config module. Every value is a DEMO SYNTHETIC
PROGNOSTICS ASSUMPTION — see `prognostics_v1.yaml`."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

DEFAULT_POLICY_PATH = Path(__file__).with_name("prognostics_v1.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DataSufficiencyPolicy(_Frozen):
    minimum_history_count: int
    rate_sign_flip_makes_unstable: bool

    @field_validator("minimum_history_count")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("data_sufficiency.minimum_history_count must be >= 1")
        return value


class PrognosticsPolicy(_Frozen):
    engine_version: str
    config_version: str
    horizons: dict[str, float]
    level_bounds: tuple[float, float]
    degradation_threshold: float
    max_crossing_horizon_seconds: float
    data_sufficiency: DataSufficiencyPolicy

    @field_validator("horizons")
    @classmethod
    def _known_horizons(cls, value: dict[str, float]) -> dict[str, float]:
        expected = {"ONE_HOUR", "SIX_HOURS", "TWENTY_FOUR_HOURS"}
        if set(value) != expected:
            raise ValueError(f"horizons must be exactly {sorted(expected)}")
        if any(v <= 0 for v in value.values()):
            raise ValueError("all horizon values must be > 0")
        return value

    @field_validator("level_bounds")
    @classmethod
    def _bounds_ordered(cls, value: tuple[float, float]) -> tuple[float, float]:
        low, high = value
        if not low < high:
            raise ValueError("level_bounds must be an ordered (low, high) pair")
        return value

    @model_validator(mode="after")
    def _threshold_within_bounds(self) -> PrognosticsPolicy:
        low, high = self.level_bounds
        if not low < self.degradation_threshold < high:
            raise ValueError("degradation_threshold must be strictly within level_bounds")
        if self.max_crossing_horizon_seconds <= 0:
            raise ValueError("max_crossing_horizon_seconds must be > 0")
        return self


_ENV_OVERRIDE = "PROGNOSTICS_POLICY_PATH"


def load_prognostics_policy(path: Path | None = None) -> PrognosticsPolicy:
    """Load and validate the prognostics policy. Raises `pydantic.ValidationError` on a
    malformed file rather than silently starting with unintended forecast thresholds."""
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return PrognosticsPolicy.model_validate(raw)
