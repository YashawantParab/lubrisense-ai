"""Bounded exponential backoff with full jitter — a pure function so it is deterministically
testable without real sleeps (Phase 5 brief §13)."""

from __future__ import annotations

import random


def compute_backoff(
    attempt: int,
    base_seconds: float = 1.0,
    factor: float = 2.0,
    max_seconds: float = 60.0,
    rng: random.Random | None = None,
) -> float:
    """Full-jitter exponential backoff (AWS-style): `uniform(0, min(max, base * factor**attempt))`.
    `attempt` is 0-indexed (0 = first retry). Always returns a value in `[0, max_seconds]` —
    never grows unbounded, never returns 0 deterministically (avoiding a tight retry loop),
    since `rng` still draws from the full interval each call."""
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    rng = rng or random.Random()
    ceiling = min(max_seconds, base_seconds * (factor**attempt))
    return rng.uniform(0.0, ceiling)
