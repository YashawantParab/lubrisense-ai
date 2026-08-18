"""MQTT -> Kafka bridge worker (Phase 6 brief §2/§3/§23; ADR-051).

Subscribes to the edge's telemetry topic wildcard (`lubrisense/v1/+/+/telemetry`, QoS 1,
matching the topic hierarchy `edge.transport.mqtt.MqttTransport` publishes to) using
`paho-mqtt`'s own network thread (`loop_start()`), and republishes each structurally valid
message onto the central Kafka telemetry topic using `aiokafka`. The two client libraries
run on different threads by design: paho-mqtt is callback/thread-based, aiokafka is
asyncio-based, so `on_message` hands each payload to the asyncio loop via
`asyncio.run_coroutine_threadsafe` rather than mixing threading models.

Never drops a structurally valid message: if Kafka is unreachable, the message is written
to a durable local SQLite spool (`spool.BridgeSpool`) instead, and a background task drains
the spool with bounded backoff once Kafka recovers (ADR-056). Structurally invalid
messages go to the Kafka DLQ topic — see `docs/TELEMETRY_PIPELINE.md`.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from datetime import UTC, datetime

import paho.mqtt.client as mqtt
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.observability.metrics import WorkerMetrics
from app.observability.worker_health import WorkerHealthServer
from app.pipeline.backoff import compute_backoff
from app.pipeline.spool import BridgeSpool
from app.pipeline.validation import SchemaValidator, ValidatedTelemetry, ValidationFailure

logger = logging.getLogger("app.pipeline.mqtt_bridge")

_SPOOL_DRAIN_BATCH_SIZE = 100
_MAX_PUBLISH_RETRIES = 3
_PUBLISH_TIMEOUT_SECONDS = 5.0


def _partition_key(tenant_id: str, gateway_id: str, sensor_id: str) -> bytes:
    """`tenant_id:gateway_id:sensor_id` (ADR-052) — preserves per-sensor-stream ordering
    within a Kafka partition."""
    return f"{tenant_id}:{gateway_id}:{sensor_id}".encode()


class MqttBridge:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._metrics = WorkerMetrics()
        self._validator = SchemaValidator(settings.pipeline_supported_schema_versions_set)
        self._spool = BridgeSpool(settings.pipeline_bridge_spool_path)

        self._loop: asyncio.AbstractEventLoop | None = None
        self._producer: AIOKafkaProducer | None = None
        self._producer_ready = False  # producer.start() has succeeded at least once
        self._kafka_reachable = False  # most recent publish attempt actually succeeded
        self._mqtt_connected = False

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined]
            client_id=f"lubrisense-mqtt-bridge-{uuid.uuid4().hex[:8]}",
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._health_server = WorkerHealthServer(
            port=settings.mqtt_bridge_health_port,
            service_name="mqtt-bridge",
            readiness_check=self._readiness,
            metrics=self._metrics,
        )

    # -- paho-mqtt callbacks (run on paho's own network thread) --------------------

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: object,
        reason_code: object,
        properties: object = None,
    ) -> None:
        reason_value = getattr(reason_code, "value", reason_code)
        self._mqtt_connected = int(reason_value) == 0  # type: ignore[call-overload]
        if self._mqtt_connected:
            logger.info("MQTT connected", extra={"topic": self._settings.mqtt_topic_pattern})
            client.subscribe(self._settings.mqtt_topic_pattern, qos=1)
        else:
            logger.error("MQTT connect failed", extra={"reason_code": str(reason_code)})

    def _on_disconnect(
        self, client: mqtt.Client, userdata: object, *args: object, **kwargs: object
    ) -> None:
        self._mqtt_connected = False
        logger.warning("MQTT disconnected")

    def _on_message(self, client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage) -> None:
        received_at = datetime.now(UTC)
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._handle_message(message.topic, bytes(message.payload), received_at), self._loop
        )

    # -- async message handling (runs on the asyncio loop) --------------------------

    async def _handle_message(self, topic: str, payload: bytes, received_at: datetime) -> None:
        self._metrics.increment("mqtt_messages_received")
        result = self._validator.validate(payload)
        if isinstance(result, ValidationFailure):
            self._metrics.increment("mqtt_invalid_messages")
            logger.warning(
                "structurally invalid telemetry message",
                extra={"reason": result.reason.value, "detail": result.detail, "mqtt_topic": topic},
            )
            await self._publish_dlq(payload, result)
            return

        await self._publish_or_spool(result, payload, received_at)

    async def _publish_or_spool(
        self, event: ValidatedTelemetry, payload: bytes, received_at: datetime
    ) -> None:
        key = _partition_key(str(event.tenant_id), event.gateway_id, str(event.sensor_id))
        headers = [
            ("mqtt_received_timestamp", received_at.isoformat().encode()),
            ("kafka_published_timestamp", datetime.now(UTC).isoformat().encode()),
        ]
        if await self._try_publish(self._settings.kafka_telemetry_topic, payload, key, headers):
            self._metrics.increment("kafka_messages_published")
            return

        self._metrics.increment("kafka_publish_failures")
        self._spool.enqueue(
            event_id=str(event.event_id),
            kafka_topic=self._settings.kafka_telemetry_topic,
            partition_key=key.decode(),
            payload=payload,
            mqtt_received_at=received_at.isoformat(),
        )
        self._metrics.set_gauge("bridge_buffer_depth", self._spool.depth())
        logger.warning("Kafka unreachable, event spooled", extra={"event_id": str(event.event_id)})

    async def _try_publish(
        self, topic: str, payload: bytes, key: bytes | None, headers: list[tuple[str, bytes]]
    ) -> bool:
        if self._producer is None or not self._producer_ready:
            return False
        for attempt in range(_MAX_PUBLISH_RETRIES):
            try:
                # `send_and_wait` alone is not a sufficient bound: against a broker that is
                # unreachable at the network/DNS level (not just returning errors), aiokafka's
                # internal metadata-refresh retry loop can spin past its own
                # `request_timeout_ms` without ever raising back to the caller. Without this
                # explicit `wait_for`, a Kafka outage would hang the publish path forever
                # instead of falling through to the durable spool (ADR-056) — observed directly
                # during the Kafka-outage acceptance test.
                await asyncio.wait_for(
                    self._producer.send_and_wait(topic, value=payload, key=key, headers=headers),
                    timeout=_PUBLISH_TIMEOUT_SECONDS,
                )
                self._kafka_reachable = True
                return True
            except (KafkaError, TimeoutError) as exc:
                logger.warning(
                    "Kafka publish attempt failed",
                    extra={"attempt": attempt, "topic": topic, "error": str(exc)},
                )
                if attempt < _MAX_PUBLISH_RETRIES - 1:
                    await asyncio.sleep(
                        compute_backoff(
                            attempt,
                            max_delay_seconds=self._settings.pipeline_retry_max_backoff_seconds,
                        )
                    )
        self._kafka_reachable = False
        return False

    async def _publish_dlq(self, payload: bytes, failure: ValidationFailure) -> None:
        headers = [
            ("reason", failure.reason.value.encode()),
            ("detail", failure.detail[:500].encode("utf-8", errors="replace")),
        ]
        published = await self._try_publish(self._settings.kafka_dlq_topic, payload, None, headers)
        if not published:
            logger.error(
                "unable to publish structurally invalid message to DLQ topic (Kafka unreachable)",
                extra={"reason": failure.reason.value},
            )

    # -- spool drain ------------------------------------------------------------------

    async def _drain_spool_loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.pipeline_bridge_spool_drain_interval_seconds)
            await self._drain_spool_once()

    async def _drain_spool_once(self) -> None:
        if self._producer is None or not self._producer_ready:
            return
        batch = self._spool.peek_batch(_SPOOL_DRAIN_BATCH_SIZE)
        for spooled in batch:
            headers = [("mqtt_received_timestamp", spooled.mqtt_received_at.encode())]
            published = await self._try_publish(
                spooled.kafka_topic, spooled.payload, spooled.partition_key.encode(), headers
            )
            if published:
                self._spool.remove(spooled.event_id)
                self._metrics.increment("kafka_messages_published")
            else:
                self._spool.mark_attempt(spooled.event_id)
                break  # Kafka still down this cycle — stop draining, retry next interval
        self._metrics.set_gauge("bridge_buffer_depth", self._spool.depth())

    # -- Kafka producer lifecycle -------------------------------------------------------

    async def _ensure_producer(self) -> None:
        if self._producer_ready:
            return
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._settings.kafka_bootstrap_servers,
                client_id="lubrisense-mqtt-bridge",
            )
        try:
            await self._producer.start()
            self._producer_ready = True
            logger.info("Kafka producer started")
        except KafkaError as exc:
            logger.warning("Kafka producer start failed, will retry", extra={"error": str(exc)})

    async def _producer_watchdog_loop(self) -> None:
        while True:
            if not self._producer_ready:
                await self._ensure_producer()
            await asyncio.sleep(5.0)

    # -- health -------------------------------------------------------------------------

    def _readiness(self) -> tuple[bool, dict[str, str]]:
        if not self._producer_ready:
            kafka_status = "unavailable"
        elif self._kafka_reachable:
            kafka_status = "reachable"
        else:
            kafka_status = "degraded"  # producer started once, but recent publishes failing
        details = {
            "mqtt": "connected" if self._mqtt_connected else "disconnected",
            "kafka_producer": kafka_status,
            "bridge_buffer_depth": str(self._spool.depth()),
        }
        # Ready as long as MQTT is up: a Kafka outage is "degraded", not "not ready" — the
        # bridge keeps accepting and durably spooling telemetry (brief §38).
        return self._mqtt_connected, details

    # -- lifecycle ------------------------------------------------------------------------

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        await self._ensure_producer()

        self._client.connect(self._settings.mqtt_host, self._settings.mqtt_port, keepalive=30)
        self._client.loop_start()
        self._health_server.start()

        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            self._loop.add_signal_handler(sig, stop_event.set)

        drain_task = asyncio.create_task(self._drain_spool_loop())
        watchdog_task = asyncio.create_task(self._producer_watchdog_loop())
        try:
            await stop_event.wait()
        finally:
            logger.info("MQTT bridge shutting down")
            drain_task.cancel()
            watchdog_task.cancel()
            self._client.loop_stop()
            self._client.disconnect()
            if self._producer is not None:
                await self._producer.stop()
            self._health_server.stop()
            self._spool.close()


async def _main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-mqtt-bridge",
    )
    bridge = MqttBridge(settings)
    await bridge.run()


if __name__ == "__main__":
    asyncio.run(_main())
