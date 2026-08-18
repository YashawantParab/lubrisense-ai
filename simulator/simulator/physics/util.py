"""Shared numerical helpers used across the physics layer."""

from __future__ import annotations

import math


def exp_relax(current: float, target: float, dt_s: float, tau_s: float) -> float:
    """First-order lag step: relax `current` toward `target` with time constant `tau_s`.

    Uses the exact exponential-decay solution (not a linear `dt/tau` Euler step) so the
    result stays stable and bounded between `current` and `target` regardless of step size
    — a large `dt` (e.g. accelerated/offline historical generation) with a linear Euler
    step can overshoot past `target` and oscillate; the exponential form cannot, by
    construction, per docs/SIMULATOR.md §15 (numerical stability across step sizes).
    """
    if tau_s <= 0:
        return target
    alpha = 1.0 - math.exp(-dt_s / tau_s)
    return current + (target - current) * alpha


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
