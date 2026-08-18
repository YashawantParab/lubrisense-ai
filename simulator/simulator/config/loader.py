"""Typed loader/validator for `demo_engineering.yaml`.

Every field maps 1:1 onto the YAML so the file remains the single source of truth for
synthetic engineering assumptions (Phase 3 brief §13); this module only adds type safety
and a validated, immutable in-memory shape for `simulator.physics.*` to consume.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG_PATH = Path(__file__).with_name("demo_engineering.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SimulationConfig(_Frozen):
    default_step_seconds: float
    default_speed_multiplier: float


class AmbientTemperatureConfig(_Frozen):
    mean: float
    daily_amplitude_c: float
    noise_std_c: float


class MachineConfig(_Frozen):
    nominal_rpm: dict[str, float]
    load_lag_time_constant_s: float
    ambient_temperature_c: AmbientTemperatureConfig


class OperatingProfileConfig(_Frozen):
    shift_windows_hours: list[tuple[float, float]]
    ramp_up_seconds: float
    ramp_down_seconds: float
    load_target_change_interval_s: float
    load_bounds_percent: tuple[float, float]
    load_band_low_max: float
    load_band_high_min: float


class ReservoirConfig(_Frozen):
    default_capacity_l: float
    low_level_warning_percent: float
    critical_level_percent: float
    empty_level_percent: float


class PumpConfig(_Frozen):
    base_operating_pressure_bar: float
    max_pressure_bar: float
    nominal_flow_capacity_cm3_min: float
    pressure_rise_time_constant_s: float
    pressure_decay_time_constant_s: float
    current_idle_a: float
    current_running_base_a: float
    current_pressure_gain_a_per_bar: float
    efficiency_default: float
    efficiency_noise_std: float


class CircuitConfig(_Frozen):
    base_resistance: float
    resistance_gain_restriction: float
    leakage_pressure_loss_gain: float
    default_restriction_factor: float
    default_leakage_factor: float
    restriction_noise_std: float


class CycleConfig(_Frozen):
    interval_minutes: float
    max_duration_s: float
    pressure_build_target_ratio: float
    piston_stroke_period_s: float
    success_delivery_ratio: float
    partial_delivery_ratio: float
    base_volume_per_cycle_cm3: float


class BearingConfig(_Frozen):
    temperature_baseline_c: float
    temperature_load_gain_c: float
    temperature_ambient_gain: float
    temperature_lubrication_gain_c: float
    temperature_lag_time_constant_s: float
    temperature_degradation_gain_c: float
    temperature_over_lubrication_gain_c: float
    vibration_baseline_mm_s: float
    vibration_load_gain_mm_s: float
    vibration_lubrication_gain_mm_s: float
    vibration_lag_time_constant_s: float
    vibration_peak_to_rms_ratio: float
    vibration_degradation_gain_mm_s: float
    lubrication_recovery_step: float
    lubrication_decay_step: float
    health_degradation_per_hour_starved: float
    health_recovery_per_hour_lubricated: float
    independent_wear_tau_s: float


class SensorModelConfig(_Frozen):
    unit: str
    noise_std: float
    bias_std: float
    resolution: float
    valid_range: tuple[float, float]


class EngineeringConfig(_Frozen):
    """Root config object — DEMO SYNTHETIC ENGINEERING ASSUMPTIONS, see
    `demo_engineering.yaml` header disclaimer and docs/SIMULATOR.md §12."""

    config_version: str
    simulation: SimulationConfig
    machine: MachineConfig
    operating_profile: OperatingProfileConfig
    reservoir: ReservoirConfig
    pump: PumpConfig
    circuit: CircuitConfig
    cycle: CycleConfig
    bearing: BearingConfig
    sensors: dict[str, SensorModelConfig]


def load_engineering_config(path: Path | None = None) -> EngineeringConfig:
    """Load and validate the synthetic engineering config. Raises `pydantic.ValidationError`
    on a malformed file rather than silently falling back to defaults — a bad config should
    fail loudly, not quietly simulate something unintended."""
    target = path or DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return EngineeringConfig.model_validate(raw)
