"""A minimal, in-process circuit breaker (Phase 27 brief §27.4) — protects genuinely
*external* dependency boundaries from being hammered by a synchronous per-request retry
storm once they start failing. Deliberately NOT applied to this platform's local,
deterministic services (the demo CMMS adapter, the hashing embedding provider) — CLAUDE.md
"Resilience" is explicit that wrapping those would add ceremony with no benefit. The one
call site that uses this today is `AgentService`'s call into whichever `LLMProvider` is
configured (`app.agent.providers.llm_provider`) — the seam that becomes a real external
network call the moment an `ExternalLLMProvider` is configured (see docs/RESILIENCE.md).

Process-local, not shared across replicas — acceptable for this reference platform's
single-backend-process demo deployment (documented limitation, `docs/RESILIENCE.md`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import TypeVar

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(RuntimeError):
    """Raised instead of calling `fn` when the breaker is `OPEN` — the caller is
    expected to degrade gracefully, exactly as it would for any other dependency
    failure."""


@dataclass
class CircuitBreaker:
    """Not thread-safe across async event loops sharing state unexpectedly — a `Lock` is
    used only to keep single-process concurrent access consistent, not for distributed
    coordination (see module docstring)."""

    name: str
    failure_threshold: int = 3
    reset_timeout_seconds: float = 30.0

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_half_open()
            return self._state

    def _maybe_half_open(self) -> None:
        if (
            self._state is CircuitState.OPEN
            and self._opened_at is not None
            and (time.monotonic() - self._opened_at) >= self.reset_timeout_seconds
        ):
            self._state = CircuitState.HALF_OPEN

    def _on_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None

    def _on_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def call(self, fn: Callable[[], T]) -> T:
        """Runs `fn()` if the breaker permits it; raises `CircuitOpenError` without
        calling `fn` at all when it does not. Re-raises whatever `fn` itself raises."""
        if self.state is CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open after {self._consecutive_failures} "
                "consecutive failures."
            )
        try:
            result = fn()
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
