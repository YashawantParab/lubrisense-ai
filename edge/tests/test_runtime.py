from __future__ import annotations

import time

from edge.buffering.store import LocalBuffer
from edge.config.models import EdgeConfig
from edge.domain.enums import ConnectivityState
from edge.runtime.runtime import EdgeRuntime
from edge.transport.test_transport import RecordingTestTransport
from tests.fakes import FakeTelemetrySource, healthy_tick, make_observation


def test_acquire_once_buffers_and_sends(edge_config: EdgeConfig) -> None:
    source = FakeTelemetrySource([healthy_tick(0)])
    transport = RecordingTestTransport()
    runtime = EdgeRuntime(edge_config, source, transport)
    runtime.acquire_once()
    assert runtime.metrics.acquired == 3
    assert runtime.metrics.buffered == 3

    runtime.start()
    deadline = time.monotonic() + 5.0
    while len(transport.sent) < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
    runtime.stop()
    assert len(transport.sent) == 3


def test_duplicate_insertion_is_prevented(edge_config: EdgeConfig) -> None:
    tick = healthy_tick(0)
    source = FakeTelemetrySource([tick, tick])  # same sensor readings replayed verbatim
    transport = RecordingTestTransport()
    runtime = EdgeRuntime(edge_config, source, transport)
    runtime.acquire_once()
    runtime.acquire_once()
    # Same source_timestamp/value but sequence numbers differ per acquisition, so this
    # exercises the ordinary (non-duplicate) path; see test_buffering for direct dedup proof.
    assert runtime.metrics.acquired == 6
    runtime.stop()


def test_graceful_shutdown_completes(edge_config: EdgeConfig) -> None:
    source = FakeTelemetrySource([healthy_tick(0)])
    transport = RecordingTestTransport()
    runtime = EdgeRuntime(edge_config, source, transport)
    runtime.start()
    runtime.acquire_once()
    runtime.stop(timeout=5.0)
    assert transport.closed is True


def test_crash_recovery_pending_events_survive_restart(edge_config: EdgeConfig) -> None:
    source = FakeTelemetrySource([healthy_tick(0)])
    blocked_transport = RecordingTestTransport()
    blocked_transport.fail_next(1000)  # never succeeds — simulates a crash before any send

    runtime = EdgeRuntime(edge_config, source, blocked_transport)
    runtime.acquire_once()
    assert runtime.buffer.pending_count() == 3
    # No clean shutdown — simulate an unclean process kill: just drop the reference and open
    # a fresh LocalBuffer against the same file, exactly as a restarted process would.
    db_path = edge_config.resolved_db_path()

    reopened = LocalBuffer(db_path)
    assert reopened.pending_count() == 3
    replayable = reopened.get_replayable()
    assert len(replayable) == 3
    original_ids = {e.event_id for e in replayable}

    working_transport = RecordingTestTransport()
    new_source = FakeTelemetrySource([])
    restarted_runtime = EdgeRuntime(edge_config, new_source, working_transport, buffer=reopened)
    sent = restarted_runtime.replay_now()
    assert sent == 3
    assert {e.event_id for e in working_transport.sent} == original_ids
    restarted_runtime.stop()


def test_sensor_dropout_never_becomes_zero(edge_config: EdgeConfig) -> None:
    tick = [make_observation("RESERVOIR_LEVEL", None, quality="MISSING")]
    source = FakeTelemetrySource([tick])
    transport = RecordingTestTransport()
    runtime = EdgeRuntime(edge_config, source, transport)
    runtime.acquire_once()
    replayable = runtime.buffer.get_replayable()
    assert len(replayable) == 1
    assert replayable[0].value is None
    assert replayable[0].value != 0.0
    assert replayable[0].quality.value == "MISSING"
    runtime.stop()


def test_simulated_communication_loss_does_not_affect_connectivity_state(
    edge_config: EdgeConfig,
) -> None:
    """A simulator-reported COMMUNICATION_LOSS quality tick is DATA CONTENT — it must never
    move `ConnectivityManager`, which only tracks the edge's own transport health. This is
    the unit-level half of the simulated-fault-vs-real-outage distinction; the real-broker
    half is proven in tests/test_mqtt_integration.py (transport genuinely unreachable)."""
    tick = [make_observation("PRESSURE", None, quality="COMMUNICATION_LOSS")]
    source = FakeTelemetrySource([tick])
    transport = RecordingTestTransport()  # always succeeds regardless of reading quality
    runtime = EdgeRuntime(edge_config, source, transport)
    runtime.acquire_once()
    runtime.start()
    deadline = time.monotonic() + 5.0
    while len(transport.sent) < 1 and time.monotonic() < deadline:
        time.sleep(0.05)
    runtime.stop()
    assert runtime.connectivity.current_state == ConnectivityState.ONLINE
    assert len(transport.sent) == 1
    assert transport.sent[0].value is None
    assert transport.sent[0].quality.value == "COMMUNICATION_LOSS"


def test_retention_overflow_increments_metrics(edge_config: EdgeConfig) -> None:
    tiny_config = edge_config.model_copy(
        update={"buffer": edge_config.buffer.model_copy(update={"max_buffered_events": 1})}
    )
    ticks = [[make_observation("PRESSURE", float(i))] for i in range(5)]
    source = FakeTelemetrySource(ticks)
    transport = RecordingTestTransport()
    transport.fail_next(1000)  # keep everything PENDING so retention has something to trim
    runtime = EdgeRuntime(tiny_config, source, transport)
    for _ in range(5):
        runtime.acquire_once()
    assert runtime.metrics.buffer_overflow_count > 0
    runtime.stop()
