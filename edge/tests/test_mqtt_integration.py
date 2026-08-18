"""Mandatory Phase 5 acceptance integration tests (brief §36-§39) — require the live
`lubrisense-mosquitto` container and the live Phase 2 database. Marked `@pytest.mark.mqtt`;
skip automatically if either is unavailable so `edge-test` still runs everywhere else.

These tests directly stop/start the SHARED dev-stack `mosquitto` container — the
`mosquitto_guaranteed_running` fixture always restores it afterward, pass or fail.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

from edge.buffering.store import LocalBuffer
from edge.config.models import EdgeConfig
from edge.runtime.runtime import EdgeRuntime
from edge.transport.mqtt import MqttTransport
from tests.conftest import FLAGSHIP_ASSET_CODE, FLAGSHIP_TENANT_ID

pytestmark = [
    pytest.mark.mqtt,
    pytest.mark.usefixtures("require_database", "require_mqtt", "mosquitto_guaranteed_running"),
]

REPO_ROOT = Path(__file__).resolve().parents[2]


class _Subscriber:
    """Subscribes before any outage and re-subscribes on every reconnect, so it is always
    already attached by the time the edge resumes publishing — no connect-after-publish race
    against the broker outage tests."""

    def __init__(self, topic: str) -> None:
        self.messages: list[bytes] = []
        self._topic = topic
        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_message = lambda _c, _u, msg: self.messages.append(msg.payload)
        self._client.on_connect = lambda c, _u, _f, _rc, _p: c.subscribe(self._topic)
        self._client.reconnect_delay_set(min_delay=1, max_delay=3)
        self._client.connect("localhost", 1883, keepalive=30)
        self._client.loop_start()

    def wait_for(self, count: int, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while len(self.messages) < count and time.monotonic() < deadline:
            time.sleep(0.1)

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


def _mqtt_edge_config(tmp_db_path: str) -> EdgeConfig:
    import uuid

    return EdgeConfig.model_validate(
        {
            "config_version": "1",
            "gateway_id": str(uuid.uuid4()),
            "gateway_code": "GW-RIDGE-CRUSH",
            "tenant_id": FLAGSHIP_TENANT_ID,
            "asset_code": FLAGSHIP_ASSET_CODE,
            "poll_interval_seconds": 0.1,
            "buffer": {
                "db_path": tmp_db_path,
                "max_buffered_events": 10000,
                "max_buffer_age_seconds": 3600,
            },
            "transport": {"mode": "mqtt", "broker_host": "localhost", "broker_port": 1883},
        }
    )


def _docker_compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=REPO_ROOT, check=True, capture_output=True)


def _wait_mosquitto_healthy(timeout: float = 30.0) -> None:
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("localhost", 1883), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError("mosquitto did not become reachable in time")


def test_simulator_to_edge_to_mqtt_end_to_end(tmp_db_path: str) -> None:
    from edge.acquisition.source import SimulatorTelemetrySource

    config = _mqtt_edge_config(tmp_db_path)
    subscriber = _Subscriber(config.resolved_topic())
    try:
        source = SimulatorTelemetrySource(asset_code=config.asset_code, seed=1)
        transport = MqttTransport(
            broker_host=config.transport.broker_host,
            broker_port=config.transport.broker_port,
            topic_template=config.transport.topic_template,
            tenant_id=config.tenant_id,
            gateway_id=config.gateway_id,
            qos=config.transport.qos,
        )
        runtime = EdgeRuntime(config, source, transport)
        runtime.start()
        try:
            runtime.run_ticks(2)
            subscriber.wait_for(1, timeout=15.0)
        finally:
            runtime.stop()
            source.close()

        assert len(subscriber.messages) >= 1
        payload = json.loads(subscriber.messages[0])
        for field in (
            "event_id",
            "sequence_number",
            "gateway_id",
            "tenant_id",
            "sensor_id",
            "measurement_type",
            "source_timestamp",
            "quality",
        ):
            assert field in payload, f"missing field {field!r} in published envelope"
        assert payload["gateway_id"] == config.gateway_id
        assert payload["tenant_id"] == config.tenant_id
    finally:
        subscriber.close()


def test_mqtt_broker_outage_buffers_then_replays_on_reconnect(tmp_db_path: str) -> None:
    """One of Phase 5's most important acceptance tests (brief §38): no event may be lost
    across a real broker outage.

    The subscriber connects and subscribes *before* the outage begins, and re-subscribes on
    every reconnect (via `on_connect`), so it is guaranteed to already be attached when the
    edge's sender thread resumes publishing — avoiding a race against a subscriber that only
    connects after the broker comes back. Buffer status (PENDING -> ACKNOWLEDGED, which the
    edge only sets after a confirmed QoS 1 puback) is the authoritative, non-flaky proof that
    every buffered event was actually delivered with its original identity; the live
    subscriber additionally confirms real messages landed on the broker.
    """
    from edge.acquisition.source import SimulatorTelemetrySource

    config = _mqtt_edge_config(tmp_db_path)
    subscriber = _Subscriber(config.resolved_topic())
    try:
        source = SimulatorTelemetrySource(asset_code=config.asset_code, seed=2)
        transport = MqttTransport(
            broker_host=config.transport.broker_host,
            broker_port=config.transport.broker_port,
            topic_template=config.transport.topic_template,
            tenant_id=config.tenant_id,
            gateway_id=config.gateway_id,
            qos=config.transport.qos,
        )
        runtime = EdgeRuntime(config, source, transport)
        runtime.start()
        try:
            runtime.run_ticks(1)
            time.sleep(2.0)  # let the first tick drain successfully
            assert runtime.metrics.sent >= 1

            _docker_compose("stop", "mosquitto")
            time.sleep(1.0)

            runtime.run_ticks(3, sleep_between_seconds=0.2)
            time.sleep(2.0)
            depth_during_outage = runtime.buffer.pending_count()
            assert depth_during_outage > 0, "buffer must grow while the broker is unreachable"

            pending_before_recovery = {e.event_id for e in runtime.buffer.get_replayable()}

            _docker_compose("start", "mosquitto")
            _wait_mosquitto_healthy()

            deadline = time.monotonic() + 30.0
            while runtime.buffer.pending_count() > 0 and time.monotonic() < deadline:
                time.sleep(0.5)

            assert runtime.buffer.pending_count() == 0, "buffer did not fully drain after reconnect"
            acknowledged = runtime.buffer.list_events(status=None, limit=1000)
            acknowledged_ids = {
                row["event_id"] for row in acknowledged if row["status"] == "ACKNOWLEDGED"
            }
            assert pending_before_recovery.issubset(acknowledged_ids), (
                "every event buffered during the outage must be ACKNOWLEDGED after replay, "
                "with its original event_id preserved — none may be lost or re-minted"
            )

            subscriber.wait_for(1, timeout=15.0)
            assert len(subscriber.messages) >= 1, "no replayed message observed on the broker"
        finally:
            runtime.stop()
            source.close()
    finally:
        subscriber.close()


def test_edge_restart_during_outage_recovers_all_pending_events(tmp_db_path: str) -> None:
    """No event should disappear merely because the edge process restarted (brief §39),
    including while the transport is a real (but unreachable) MQTT broker."""
    from edge.acquisition.source import SimulatorTelemetrySource

    config = _mqtt_edge_config(tmp_db_path)
    _docker_compose("stop", "mosquitto")
    time.sleep(1.0)
    try:
        source = SimulatorTelemetrySource(asset_code=config.asset_code, seed=3)
        try:
            transport = MqttTransport(
                broker_host=config.transport.broker_host,
                broker_port=config.transport.broker_port,
                topic_template=config.transport.topic_template,
                tenant_id=config.tenant_id,
                gateway_id=config.gateway_id,
                qos=config.transport.qos,
            )
        except Exception:
            transport = None  # connect() may itself fail while the broker is down
        if transport is None:
            from edge.transport.noop import NoopTransport

            transport = NoopTransport()  # placeholder; acquisition below does not depend on it

        buffer = LocalBuffer(config.resolved_db_path())
        runtime = EdgeRuntime(config, source, transport, buffer=buffer)
        runtime.acquire_once()
        runtime.acquire_once()
        pending_before = runtime.buffer.pending_count()
        assert pending_before > 0
        original_ids = {e.event_id for e in runtime.buffer.get_replayable()}
        source.close()
        # No clean shutdown — simulate a crash: reopen a fresh buffer against the same file.

        reopened = LocalBuffer(config.resolved_db_path())
        assert reopened.pending_count() == pending_before
        assert {e.event_id for e in reopened.get_replayable()} == original_ids
    finally:
        _docker_compose("start", "mosquitto")
        _wait_mosquitto_healthy()

    subscriber = _Subscriber(config.resolved_topic())
    try:
        real_transport = MqttTransport(
            broker_host=config.transport.broker_host,
            broker_port=config.transport.broker_port,
            topic_template=config.transport.topic_template,
            tenant_id=config.tenant_id,
            gateway_id=config.gateway_id,
            qos=config.transport.qos,
        )
        recovered_source = SimulatorTelemetrySource(asset_code=config.asset_code, seed=3)
        recovered_runtime = EdgeRuntime(config, recovered_source, real_transport, buffer=reopened)
        sent = recovered_runtime.replay_now()
        assert sent == pending_before
        subscriber.wait_for(pending_before, timeout=15.0)
        received_ids = {json.loads(m)["event_id"] for m in subscriber.messages}
        assert original_ids.issubset(received_ids)
        recovered_runtime.stop()
        recovered_source.close()
    finally:
        subscriber.close()
