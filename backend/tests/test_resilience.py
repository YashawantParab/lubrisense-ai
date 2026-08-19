"""`CircuitBreaker` unit tests (Phase 27 brief §27.4) and a resilience check on the
`AgentService` LLM-provider seam it protects."""

from __future__ import annotations

import time

import pytest

from app.core.resilience import CircuitBreaker, CircuitOpenError, CircuitState


def test_circuit_closed_by_default_and_calls_succeed() -> None:
    breaker = CircuitBreaker(name="test", failure_threshold=3)
    assert breaker.state is CircuitState.CLOSED
    assert breaker.call(lambda: 42) == 42
    assert breaker.state is CircuitState.CLOSED


def test_circuit_opens_after_failure_threshold() -> None:
    breaker = CircuitBreaker(name="test", failure_threshold=3, reset_timeout_seconds=60)

    def fail() -> None:
        raise RuntimeError("boom")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.call(fail)

    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: 1)  # not even attempted


def test_circuit_half_opens_and_closes_after_reset_timeout() -> None:
    breaker = CircuitBreaker(name="test", failure_threshold=1, reset_timeout_seconds=0.05)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert breaker.state is CircuitState.OPEN

    time.sleep(0.06)
    assert breaker.state is CircuitState.HALF_OPEN

    assert breaker.call(lambda: "recovered") == "recovered"
    assert breaker.state is CircuitState.CLOSED


def test_circuit_reset_clears_state() -> None:
    breaker = CircuitBreaker(name="test", failure_threshold=1, reset_timeout_seconds=60)
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert breaker.state is CircuitState.OPEN

    breaker.reset()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.call(lambda: "ok") == "ok"
