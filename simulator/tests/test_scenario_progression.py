from __future__ import annotations

from simulator.scenarios.progression import compute_severity
from simulator.scenarios.types import ProgressionType


def test_step_is_instantly_full_severity() -> None:
    assert compute_severity(ProgressionType.STEP, 0.0, 3600.0) == 1.0
    assert compute_severity(ProgressionType.STEP, 100.0, 3600.0) == 1.0


def test_negative_elapsed_is_zero_for_every_profile() -> None:
    for profile in ProgressionType:
        assert compute_severity(profile, -1.0, 3600.0) == 0.0


def test_linear_ramps_evenly() -> None:
    assert compute_severity(ProgressionType.LINEAR, 0.0, 100.0) == 0.0
    assert compute_severity(ProgressionType.LINEAR, 50.0, 100.0) == 0.5
    assert compute_severity(ProgressionType.LINEAR, 100.0, 100.0) == 1.0
    assert compute_severity(ProgressionType.LINEAR, 200.0, 100.0) == 1.0  # clipped


def test_exponential_approaches_but_starts_slow() -> None:
    early = compute_severity(ProgressionType.EXPONENTIAL, 10.0, 300.0)
    late = compute_severity(ProgressionType.EXPONENTIAL, 290.0, 300.0)
    assert 0.0 < early < 0.5
    assert late > 0.9


def test_sigmoid_is_slow_then_fast_then_slow() -> None:
    start = compute_severity(ProgressionType.SIGMOID, 0.0, 1000.0)
    mid = compute_severity(ProgressionType.SIGMOID, 500.0, 1000.0)
    end = compute_severity(ProgressionType.SIGMOID, 1000.0, 1000.0)
    assert start < 0.1
    assert abs(mid - 0.5) < 0.05
    assert end > 0.9


def test_sigmoid_is_monotonically_increasing() -> None:
    samples = [compute_severity(ProgressionType.SIGMOID, t, 1000.0) for t in range(0, 1001, 50)]
    assert all(b >= a for a, b in zip(samples, samples[1:], strict=False))


def test_intermittent_square_wave() -> None:
    # period=100, duty_cycle=0.3 -> ON for [0,30), OFF for [30,100)
    assert (
        compute_severity(ProgressionType.INTERMITTENT, 0.0, 0.0, period_s=100.0, duty_cycle=0.3)
        == 1.0
    )
    assert (
        compute_severity(ProgressionType.INTERMITTENT, 29.0, 0.0, period_s=100.0, duty_cycle=0.3)
        == 1.0
    )
    assert (
        compute_severity(ProgressionType.INTERMITTENT, 31.0, 0.0, period_s=100.0, duty_cycle=0.3)
        == 0.0
    )
    assert (
        compute_severity(ProgressionType.INTERMITTENT, 129.0, 0.0, period_s=100.0, duty_cycle=0.3)
        == 1.0
    )


def test_intermittent_is_deterministic_pure_function_of_time() -> None:
    """No RNG parameter exists on compute_severity — calling it twice with the same
    arguments must be identical, which is the whole determinism guarantee for progression
    (docs/SCENARIO_ENGINE.md)."""
    a = compute_severity(ProgressionType.INTERMITTENT, 1234.5, 0.0, period_s=300.0, duty_cycle=0.4)
    b = compute_severity(ProgressionType.INTERMITTENT, 1234.5, 0.0, period_s=300.0, duty_cycle=0.4)
    assert a == b


def test_cyclic_oscillates_between_0_and_1() -> None:
    values = [
        compute_severity(ProgressionType.CYCLIC, t, 0.0, period_s=100.0) for t in range(0, 101, 5)
    ]
    assert min(values) < 0.05
    assert max(values) > 0.95


def test_all_profiles_stay_within_0_1() -> None:
    for profile in ProgressionType:
        for t in range(0, 2000, 37):
            severity = compute_severity(
                profile, float(t), 500.0, period_s=200.0, duty_cycle=0.4, sigmoid_steepness=6.0
            )
            assert 0.0 <= severity <= 1.0
