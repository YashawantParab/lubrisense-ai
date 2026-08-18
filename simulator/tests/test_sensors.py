from __future__ import annotations

import random
import statistics

from simulator.config.loader import SensorModelConfig
from simulator.domain.enums import SensorQuality
from simulator.sensors import models

NOISY_CONFIG = SensorModelConfig(
    unit="bar", noise_std=0.05, bias_std=0.03, resolution=0.01, valid_range=(0.0, 25.0)
)
NOISE_FREE_CONFIG = SensorModelConfig(
    unit="boolean", noise_std=0.0, bias_std=0.0, resolution=1.0, valid_range=(0.0, 1.0)
)


def test_observation_close_to_true_value_within_noise_bounds() -> None:
    rng = random.Random(0)
    obs = models.observe(9.0, bias=0.0, config=NOISY_CONFIG, rng=rng)
    assert abs(obs.observed_value - 9.0) < 1.0
    assert obs.true_value == 9.0
    assert obs.unit == "bar"


def test_observation_respects_resolution_quantization() -> None:
    rng = random.Random(0)
    obs = models.observe(9.123456, bias=0.0, config=NOISY_CONFIG, rng=rng)
    scaled = obs.observed_value / NOISY_CONFIG.resolution
    assert abs(scaled - round(scaled)) < 1e-9


def test_observation_clipped_to_valid_range() -> None:
    rng = random.Random(0)
    obs = models.observe(1000.0, bias=0.0, config=NOISY_CONFIG, rng=rng)
    assert obs.observed_value <= NOISY_CONFIG.valid_range[1]
    assert obs.quality == SensorQuality.SUSPECT


def test_observation_within_range_is_good_quality() -> None:
    rng = random.Random(0)
    obs = models.observe(9.0, bias=0.0, config=NOISY_CONFIG, rng=rng)
    assert obs.quality == SensorQuality.GOOD


def test_bias_shifts_observation_consistently() -> None:
    rng = random.Random(0)
    obs_no_bias = models.observe(
        9.0,
        bias=0.0,
        config=NOISE_FREE_CONFIG.model_copy(update={"valid_range": (0.0, 100.0)}),
        rng=rng,
    )
    obs_with_bias = models.observe(
        9.0,
        bias=2.0,
        config=NOISE_FREE_CONFIG.model_copy(update={"valid_range": (0.0, 100.0)}),
        rng=random.Random(0),
    )
    assert obs_with_bias.observed_value - obs_no_bias.observed_value == 2.0


def test_noise_free_boolean_sensor_passes_through_exactly() -> None:
    rng = random.Random(0)
    obs = models.observe(1.0, bias=0.0, config=NOISE_FREE_CONFIG, rng=rng)
    assert obs.observed_value == 1.0
    obs_zero = models.observe(0.0, bias=0.0, config=NOISE_FREE_CONFIG, rng=rng)
    assert obs_zero.observed_value == 0.0


def test_draw_initial_bias_is_deterministic_for_seed() -> None:
    bias_a = models.draw_initial_bias(NOISY_CONFIG, random.Random(123))
    bias_b = models.draw_initial_bias(NOISY_CONFIG, random.Random(123))
    assert bias_a == bias_b


def test_noise_profile_differs_by_sensor_type() -> None:
    """Different measurement types must not all get identical noise application (Phase 3
    brief §11: "Do not add identical Gaussian noise to every signal without thought")."""
    tight_config = SensorModelConfig(
        unit="A", noise_std=0.01, bias_std=0.0, resolution=0.01, valid_range=(0.0, 10.0)
    )
    loose_config = SensorModelConfig(
        unit="cm3/min", noise_std=3.0, bias_std=0.0, resolution=0.1, valid_range=(0.0, 500.0)
    )
    rng_tight = random.Random(42)
    rng_loose = random.Random(42)
    tight_spread = [
        models.observe(5.0, 0.0, tight_config, rng_tight).observed_value for _ in range(200)
    ]
    loose_spread = [
        models.observe(5.0, 0.0, loose_config, rng_loose).observed_value for _ in range(200)
    ]
    assert statistics.pstdev(loose_spread) > statistics.pstdev(tight_spread) * 10
