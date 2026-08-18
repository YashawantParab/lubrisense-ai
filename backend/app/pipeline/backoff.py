"""Bounded exponential backoff with full jitter.

A small, local reimplementation of the same pattern the edge uses
(`edge.connectivity.backoff.compute_backoff`) — kept independent rather than shared, per
ADR-059 (the central pipeline does not depend on the `edge` package).
"""

from __future__ import annotations

import random

BASE_DELAY_SECONDS = 0.5


def compute_backoff(
    attempt: int, *, max_delay_seconds: float, rng: random.Random | None = None
) -> float:
    """`attempt` is 0-indexed (0 = first retry). Full jitter: `random(0, min(max, base*2^n))`."""
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    rng = rng or random.Random()  # noqa: S311 - retry jitter, not cryptographic
    ceiling = min(max_delay_seconds, BASE_DELAY_SECONDS * (2**attempt))
    return rng.uniform(0, ceiling)
