"""`EdgeRuntime` — one acquisition loop + one background sender thread, coordinated by a
single coarse-grained lock around buffer access (Phase 5 brief §31-§33).

This is deliberately the simplest concurrency model that is still correct: one gateway's
demo-scale event rate (a handful of sensors, one poll every few seconds) does not need a
thread pool, a work queue, or async I/O. A single `threading.Lock` around every buffer call
is not a high-throughput design — it is a small, obviously-correct one, which is what this
phase's acceptance criteria (crash recovery, no lost events, no duplicate rows) actually
need (see docs/EDGE_ARCHITECTURE.md "Concurrency model").
"""

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import UTC, datetime, timedelta

from edge.acquisition.builder import EnvelopeBuilder
from edge.acquisition.source import TelemetrySource
from edge.buffering.store import LocalBuffer
from edge.config.models import EdgeConfig
from edge.connectivity.backoff import compute_backoff
from edge.connectivity.manager import ConnectivityManager
from edge.domain.alert import LocalEdgeAlert
from edge.domain.enums import ConnectivityState
from edge.health.metrics import EdgeMetrics
from edge.health.snapshot import EdgeHealth, build_health_snapshot
from edge.rules.engine import LocalRuleEngine
from edge.transport.base import EdgeTransport, TransportError

logger = logging.getLogger("edge.runtime")

_SENDER_IDLE_POLL_SECONDS = 0.2


class EdgeRuntime:
    def __init__(
        self,
        config: EdgeConfig,
        source: TelemetrySource,
        transport: EdgeTransport,
        buffer: LocalBuffer | None = None,
    ) -> None:
        self._config = config
        self._source = source
        self._transport = transport
        self._buffer = buffer or LocalBuffer(config.resolved_db_path())
        self._builder = EnvelopeBuilder(config, self._buffer)
        self._rules = LocalRuleEngine(config.rule_thresholds)
        self._connectivity = ConnectivityManager()
        self._metrics = EdgeMetrics()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._sender_thread: threading.Thread | None = None
        self._last_acquisition_time: datetime | None = None
        self._alerts: list[LocalEdgeAlert] = []
        self._runtime_status = "STOPPED"
        self._rng = random.Random()
        self._record_config_version()

    def _record_config_version(self) -> None:
        previous = self._buffer.get_config_version(self._config.gateway_id)
        if previous != self._config.config_version:
            logger.info(
                "edge config version changed gateway_id=%s %s -> %s",
                self._config.gateway_id,
                previous,
                self._config.config_version,
            )
            self._metrics.config_changes += 1
            self._buffer.set_config_version(self._config.gateway_id, self._config.config_version)

    # -- lifecycle ---------------------------------------------------------------

    def start(self) -> None:
        self._runtime_status = "RUNNING"
        self._stop_event.clear()
        self._sender_thread = threading.Thread(
            target=self._sender_loop, name="edge-sender", daemon=True
        )
        self._sender_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Graceful shutdown (§33): stop acquisition, let the sender thread finish/abort its
        current attempt, commit buffer state, close transport and DB."""
        self._runtime_status = "STOPPING"
        self._stop_event.set()
        if self._sender_thread is not None:
            self._sender_thread.join(timeout=timeout)
        self._transport.close()
        self._buffer.close()
        self._runtime_status = "STOPPED"

    def __enter__(self) -> EdgeRuntime:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    # -- acquisition ---------------------------------------------------------------

    def acquire_once(self) -> list[LocalEdgeAlert]:
        observations = self._source.poll()
        self._last_acquisition_time = datetime.now(UTC)
        new_alerts: list[LocalEdgeAlert] = []
        for observation in observations:
            with self._lock:
                # `EnvelopeBuilder.build()` calls `LocalBuffer.next_sequence()`, which shares
                # the same sqlite3 connection the sender thread uses — it must be under the
                # same lock as every other buffer call, not just `insert_pending` (a real bug
                # caught during Docker verification: concurrent unlocked/locked access to one
                # sqlite3.Connection from two threads raised sqlite3.DatabaseError).
                envelope = self._builder.build(observation)
                self._metrics.acquired += 1
                inserted = self._buffer.insert_pending(envelope)
                if inserted:
                    self._metrics.buffered += 1
                else:
                    self._metrics.duplicates_prevented += 1
                overflow = self._buffer.enforce_retention(
                    self._config.buffer.max_buffered_events,
                    self._config.buffer.max_buffer_age_seconds,
                )
            if overflow:
                self._metrics.buffer_overflow_count += overflow
                self._metrics.warnings += 1
                logger.warning(
                    "buffer retention breach: moved %d event(s) to DEAD_LETTER", overflow
                )
            for alert in self._rules.evaluate(envelope):
                self._alerts.append(alert)
                new_alerts.append(alert)
                self._metrics.warnings += 1
        return new_alerts

    def run_ticks(self, count: int, sleep_between_seconds: float = 0.0) -> None:
        for _ in range(count):
            if self._stop_event.is_set():
                break
            self.acquire_once()
            if sleep_between_seconds:
                time.sleep(sleep_between_seconds)

    # -- sending / replay ------------------------------------------------------

    def _sender_loop(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            sent_this_pass = self._drain_once()
            if sent_this_pass > 0:
                attempt = 0
                continue
            delay = compute_backoff(attempt, base_seconds=0.5, max_seconds=10.0, rng=self._rng)
            attempt = min(attempt + 1, 20)
            self._stop_event.wait(max(delay, _SENDER_IDLE_POLL_SECONDS))

    def _drain_once(self) -> int:
        """One drain pass: send everything currently PENDING/FAILED, stop at the first
        failure (the outer loop will back off and retry). Returns count sent."""
        with self._lock:
            pending = self._buffer.get_replayable(limit=200)
        sent = 0
        for envelope in pending:
            if self._stop_event.is_set():
                break
            is_replay = self._connectivity.current_state in (
                ConnectivityState.OFFLINE,
                ConnectivityState.RECOVERING,
            )
            emitted_at = datetime.now(UTC) + timedelta(seconds=self._config.clock_offset_seconds)
            outgoing = envelope.with_emitted_now(emitted_at)
            try:
                self._transport.send(outgoing)
            except TransportError as exc:
                with self._lock:
                    self._buffer.mark_failed(envelope.event_id, str(exc))
                self._connectivity.record_failure()
                self._metrics.failures += 1
                break
            with self._lock:
                self._buffer.mark_sent(envelope.event_id, payload=outgoing.to_json())
                self._buffer.mark_acknowledged(envelope.event_id)
            self._connectivity.record_success()
            self._metrics.sent += 1
            if is_replay:
                self._metrics.replayed += 1
            sent += 1
        return sent

    def replay_now(self) -> int:
        """Manual, synchronous replay pass (used by `python -m edge replay` and tests) —
        distinct from the always-running background sender thread."""
        total = 0
        while True:
            sent = self._drain_once()
            total += sent
            if sent == 0:
                break
        return total

    # -- health ---------------------------------------------------------------

    def health_snapshot(self) -> EdgeHealth:
        with self._lock:
            buffer_depth = self._buffer.pending_count()
            oldest_age = self._buffer.oldest_pending_age_seconds()
        return build_health_snapshot(
            runtime_status=self._runtime_status,
            gateway_id=self._config.gateway_id,
            connected_sensor_count=getattr(self._source, "sensor_count", 0),
            last_acquisition_time=self._last_acquisition_time,
            buffer_depth=buffer_depth,
            oldest_buffered_event_age_seconds=oldest_age,
            connectivity=self._connectivity,
            open_local_alert_count=self._rules.open_alert_count,
            config_version=self._config.config_version,
            firmware_version=self._config.firmware_version,
            metrics=self._metrics,
        )

    @property
    def buffer(self) -> LocalBuffer:
        return self._buffer

    @property
    def connectivity(self) -> ConnectivityManager:
        return self._connectivity

    @property
    def metrics(self) -> EdgeMetrics:
        return self._metrics
