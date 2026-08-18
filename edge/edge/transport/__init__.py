"""Transport abstraction — `EdgeTransport` protocol + `NoopTransport`/`RecordingTestTransport`/
`MqttTransport` implementations (Phase 5 brief §14-§15; ADR-046)."""

from edge.transport.base import EdgeTransport, TransportError
from edge.transport.mqtt import MqttTransport
from edge.transport.noop import NoopTransport
from edge.transport.test_transport import RecordingTestTransport

__all__ = [
    "EdgeTransport",
    "TransportError",
    "NoopTransport",
    "RecordingTestTransport",
    "MqttTransport",
]
