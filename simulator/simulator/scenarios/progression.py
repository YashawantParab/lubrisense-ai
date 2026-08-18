"""Reusable progression profiles (Phase 4 brief §4): pure functions mapping elapsed
scenario time to a severity in [0.0, 1.0]. The scenario definition scales this generic
severity by its own effect-specific magnitude (e.g. "0.0-1.0 severity" -> "restriction_factor
0.0-0.85") — this module only shapes *timing*, never physical units.

All profiles are deterministic pure functions of elapsed time (no RNG) — including
`INTERMITTENT`'s duty-cycle square wave — so scenario progression never itself threatens
determinism (docs/SIMULATOR.md §13); only sensor noise and healthy natural-variation do.
"""

from __future__ import annotations

import math

from simulator.scenarios.types import ProgressionType


def compute_severity(
    profile: ProgressionType,
    elapsed_s: float,
    onset_seconds: float,
    *,
    period_s: float = 0.0,
    duty_cycle: float = 0.5,
    sigmoid_steepness: float = 6.0,
) -> float:
    """Severity in [0.0, 1.0] as a function of `elapsed_s` since the scenario became ACTIVE.

    - `STEP`: instantly at full severity — for abrupt faults (Sudden Blockage), where a
      near-instantaneous change is the point of the scenario (Phase 3 brief §5 permits
      instantaneous jumps "unless simulating a fault" — this is that exception).
    - `LINEAR`: ramps 0 -> 1 evenly over `onset_seconds`.
    - `EXPONENTIAL`: approaches 1 with time constant `onset_seconds / 3` (~95% reached by
      `onset_seconds`) — a slow start that accelerates, matching gradual mechanical wear.
    - `SIGMOID`: S-curve centered at `onset_seconds / 2` — slow onset, fast middle
      transition, slow approach to full severity; a common shape for a "developing" fault.
    - `INTERMITTENT`: deterministic square wave, `duty_cycle` fraction of each `period_s`
      window at severity 1.0, otherwise 0.0 — for on/off faults (Sensor Dropout, Network
      Failure) rather than a continuously-growing one.
    - `CYCLIC`: smooth 0 <-> 1 oscillation with period `period_s` (raised cosine) — reserved
      for future scenario types with a naturally periodic severity; none of the Phase 4
      catalog scenarios default to it, but it is fully supported and tested.
    """
    if elapsed_s < 0:
        return 0.0

    if profile == ProgressionType.STEP:
        return 1.0

    if profile == ProgressionType.LINEAR:
        if onset_seconds <= 0:
            return 1.0
        return _clip01(elapsed_s / onset_seconds)

    if profile == ProgressionType.EXPONENTIAL:
        if onset_seconds <= 0:
            return 1.0
        tau = max(onset_seconds / 3.0, 1e-6)
        return _clip01(1.0 - math.exp(-elapsed_s / tau))

    if profile == ProgressionType.SIGMOID:
        if onset_seconds <= 0:
            return 1.0
        midpoint = onset_seconds / 2.0
        x = (elapsed_s - midpoint) / max(onset_seconds / sigmoid_steepness, 1e-6)
        return _clip01(1.0 / (1.0 + math.exp(-x)))

    if profile == ProgressionType.INTERMITTENT:
        if period_s <= 0:
            return 1.0
        phase = (elapsed_s % period_s) / period_s
        return 1.0 if phase < duty_cycle else 0.0

    if profile == ProgressionType.CYCLIC:
        if period_s <= 0:
            return 0.0
        return _clip01(0.5 * (1.0 - math.cos(2.0 * math.pi * elapsed_s / period_s)))

    raise ValueError(f"Unknown progression profile: {profile}")  # pragma: no cover


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
