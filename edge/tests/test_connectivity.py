from __future__ import annotations

import random

from edge.connectivity.backoff import compute_backoff
from edge.connectivity.manager import ConnectivityManager
from edge.domain.enums import ConnectivityState


def test_backoff_is_bounded() -> None:
    rng = random.Random(1)
    for attempt in range(20):
        delay = compute_backoff(attempt, base_seconds=1.0, factor=2.0, max_seconds=30.0, rng=rng)
        assert 0.0 <= delay <= 30.0


def test_backoff_grows_with_attempt_on_average() -> None:
    rng = random.Random(7)
    early = [compute_backoff(0, max_seconds=100.0, rng=rng) for _ in range(50)]
    late = [compute_backoff(8, max_seconds=100.0, rng=rng) for _ in range(50)]
    assert sum(late) / len(late) > sum(early) / len(early)


def test_backoff_is_deterministic_given_seeded_rng() -> None:
    a = compute_backoff(3, rng=random.Random(42))
    b = compute_backoff(3, rng=random.Random(42))
    assert a == b


def test_connectivity_starts_online() -> None:
    mgr = ConnectivityManager()
    assert mgr.current_state == ConnectivityState.ONLINE


def test_connectivity_degrades_before_going_offline() -> None:
    mgr = ConnectivityManager(offline_after_failures=3)
    mgr.record_failure()
    assert mgr.current_state == ConnectivityState.DEGRADED
    mgr.record_failure()
    assert mgr.current_state == ConnectivityState.DEGRADED
    mgr.record_failure()
    assert mgr.current_state == ConnectivityState.OFFLINE


def test_connectivity_recovers_through_recovering_state() -> None:
    mgr = ConnectivityManager(offline_after_failures=2, recovered_after_successes=2)
    mgr.record_failure()
    mgr.record_failure()
    assert mgr.current_state == ConnectivityState.OFFLINE

    mgr.record_success()
    assert mgr.current_state == ConnectivityState.RECOVERING
    mgr.record_success()
    assert mgr.current_state == ConnectivityState.ONLINE


def test_connectivity_failure_resets_consecutive_successes() -> None:
    mgr = ConnectivityManager()
    mgr.record_success()
    mgr.record_failure()
    assert mgr.consecutive_successes == 0
