"""`NoopTransport` — always succeeds and discards, for local dev/demo without a broker."""

from __future__ import annotations

import logging

from edge.domain.envelope import ReadingEnvelope

logger = logging.getLogger("edge.transport.noop")


class NoopTransport:
    def send(self, envelope: ReadingEnvelope) -> None:
        logger.debug("noop transport discarding event_id=%s", envelope.event_id)

    def health(self) -> bool:
        return True

    def close(self) -> None:
        pass
