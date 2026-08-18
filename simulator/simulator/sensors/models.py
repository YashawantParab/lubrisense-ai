"""Generic sensor model: `observed = true_value + bias + noise`, then quantized to
`resolution` and clipped to `valid_range` (Phase 3 brief §11-§12).

Every measurement type gets its own noise/bias/resolution/valid_range from
`demo_engineering.yaml::sensors` (config-driven, not one Gaussian applied blindly
everywhere — e.g. `CYCLE_COMPLETION`/`PISTON_MOVEMENT` are configured noise-free since they
are discrete/counter signals, not continuous analog measurements).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulator.config.loader import SensorModelConfig
from simulator.domain.enums import SensorQuality
from simulator.physics.util import clip


@dataclass(frozen=True, slots=True)
class SensorObservation:
    true_value: float
    observed_value: float
    unit: str
    quality: SensorQuality


def draw_initial_bias(config: SensorModelConfig, rng: random.Random) -> float:
    """A sensor's bias is fixed for the life of a simulation run (drawn once at setup from
    the configured bias_std), not re-rolled every tick — modeling a fixed calibration
    offset rather than additional noise (docs/SIMULATOR.md §11)."""
    return rng.gauss(0.0, config.bias_std)


def observe(
    true_value: float, bias: float, config: SensorModelConfig, rng: random.Random
) -> SensorObservation:
    noisy = true_value + bias + rng.gauss(0.0, config.noise_std)
    if config.resolution > 0:
        quantized = round(noisy / config.resolution) * config.resolution
    else:
        quantized = noisy
    low, high = config.valid_range
    clipped = clip(quantized, low, high)
    quality = SensorQuality.GOOD if quantized == clipped else SensorQuality.SUSPECT
    return SensorObservation(
        true_value=true_value, observed_value=clipped, unit=config.unit, quality=quality
    )
