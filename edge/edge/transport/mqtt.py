"""`MqttTransport` — real MQTT publish via `paho-mqtt` (Phase 5 brief §15; ADR-046).

Topic: `lubrisense/v1/{tenant_id}/{gateway_id}/telemetry` (one topic per gateway; a real
central subscriber would use a wildcard `lubrisense/v1/+/+/telemetry`). QoS 1 (at-least-once)
— see ADR-046 for the full rationale (broker-side persistence covers store-and-forward
durability; consumer-side `event_id` dedup already handles any duplicate delivery QoS 2
would otherwise exist to prevent, so QoS 2's extra handshake buys nothing here; QoS 0 can
silently drop on a flaky link, defeating the point of this whole phase).
"""

from __future__ import annotations

import logging
import uuid

import paho.mqtt.client as mqtt

from edge.domain.envelope import ReadingEnvelope, dumps_for_transport
from edge.transport.base import TransportError

logger = logging.getLogger("edge.transport.mqtt")

_PUBLISH_TIMEOUT_SECONDS = 5.0


class MqttTransport:
    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        topic_template: str,
        tenant_id: str,
        gateway_id: str,
        qos: int = 1,
        client_id: str | None = None,
    ) -> None:
        self._topic = topic_template.format(tenant_id=tenant_id, gateway_id=gateway_id)
        self._qos = qos
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined]
            client_id=client_id or f"edge-{gateway_id}-{uuid.uuid4().hex[:8]}",
        )
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._connected = False
        self._connect()

    def _connect(self) -> None:
        try:
            self._client.connect(self._broker_host, self._broker_port, keepalive=30)
            self._client.loop_start()
            self._connected = True
        except OSError as exc:
            self._connected = False
            raise TransportError(f"MQTT connect failed: {exc}") from exc

    def send(self, envelope: ReadingEnvelope) -> None:
        if not self._connected:
            self._connect()
        payload = dumps_for_transport(envelope)
        try:
            info = self._client.publish(self._topic, payload, qos=self._qos)
            info.wait_for_publish(timeout=_PUBLISH_TIMEOUT_SECONDS)
            if not info.is_published():
                raise TransportError(f"publish not confirmed for event_id={envelope.event_id}")
        except (OSError, RuntimeError, ValueError) as exc:
            self._connected = False
            raise TransportError(f"MQTT publish failed: {exc}") from exc

    def health(self) -> bool:
        return self._connected and self._client.is_connected()

    def close(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001 — best-effort shutdown, never raise on close
            logger.debug("MQTT transport close encountered an error", exc_info=True)
        self._connected = False
