"""`RecordingTestTransport` — in-memory transport for unit tests, with a settable failure
mode so `ConnectivityManager`/retry/replay behavior can be tested without a real broker."""

from __future__ import annotations

from edge.domain.envelope import ReadingEnvelope
from edge.transport.base import TransportError


class RecordingTestTransport:
    def __init__(self) -> None:
        self.sent: list[ReadingEnvelope] = []
        self.healthy = True
        self.fail_next_n = 0
        self.closed = False

    def send(self, envelope: ReadingEnvelope) -> None:
        if self.fail_next_n > 0:
            self.fail_next_n -= 1
            raise TransportError("simulated transport failure")
        self.sent.append(envelope)

    def health(self) -> bool:
        return self.healthy

    def close(self) -> None:
        self.closed = True

    def fail_next(self, n: int) -> None:
        self.fail_next_n = n
