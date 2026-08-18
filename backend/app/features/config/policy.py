"""Validated Phase 10 feature-computation policy."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class FeaturePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str
    maximum_lookback_seconds: int = Field(gt=0, le=604800)
    maximum_rows_per_vector: int = Field(gt=0)
    denominator_epsilon: float = Field(gt=0)
    late_arrival_seconds: float = Field(gt=0)
    deviation_mad_multiplier: float = Field(gt=0)
    pressure_cycle_idle_threshold: float = Field(ge=0)
    slope_max_points: int = Field(ge=3, le=501)
    worker_cycle_seconds: float = Field(gt=0)
    load_low_upper_percent: float = Field(ge=0)
    load_normal_upper_percent: float = Field(gt=0)
    rpm_stopped_upper: float = Field(ge=0)
    rpm_low_upper: float = Field(gt=0)
    rpm_nominal_upper: float = Field(gt=0)


@lru_cache
def load_feature_policy(path: str | None = None) -> FeaturePolicy:
    configured = path or os.getenv("FEATURE_POLICY_PATH")
    policy_path = (
        Path(configured) if configured else Path(__file__).with_name("demo_feature_policy.yaml")
    )
    with policy_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return FeaturePolicy.model_validate(raw)
