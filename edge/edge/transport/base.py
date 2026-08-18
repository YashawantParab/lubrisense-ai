"""`EdgeTransport` protocol — Phase 6 (or a future real-device Phase) may add a Kafka-bridge
or other transport; this boundary is what makes that swap not touch acquisition/buffering
code (Phase 5 brief §14)."""

from __future__ import annotations

from typing import Protocol

from edge.domain.envelope import ReadingEnvelope


class TransportError(RuntimeError):
    """Raised by `EdgeTransport.send()` on any delivery failure (broker unreachable,
    connect refused, publish timeout, ...). Never raised for a routine business condition —
    those are represented as data (quality tags), not exceptions."""


class EdgeTransport(Protocol):
    def send(self, envelope: ReadingEnvelope) -> None:
        """Deliver one event. Raises `TransportError` on failure; the caller (the edge's
        sender loop) is responsible for buffering/retry — this method does not retry."""
        ...

    def health(self) -> bool:
        """Best-effort liveness check, independent of `send()` — used by
        `edge.runtime.EdgeRuntime` to decide whether to attempt a drain pass."""
        ...

    def close(self) -> None:
        """Release any held resources (sockets, client handles). Idempotent."""
        ...
