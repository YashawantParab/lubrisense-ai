"""`ConnectivityManager` — four-state connectivity model (Phase 5 brief §12; ADR-048).

ONLINE -> (>=1 failure) -> DEGRADED -> (>= offline_after_failures consecutive failures) ->
OFFLINE -> (first success) -> RECOVERING -> (>= recovered_after_successes consecutive
successes) -> ONLINE.

This tracks *transport* health only (an actual MQTT broker being reachable) — it has no
knowledge of the simulator's own `NetworkState`/`quality=COMMUNICATION_LOSS` scenario data,
which is a completely different, data-content-only concept (docs/EDGE_ARCHITECTURE.md
"Simulated fault vs. real transport outage").
"""

from __future__ import annotations

from datetime import UTC, datetime

from edge.domain.enums import ConnectivityState


class ConnectivityManager:
    def __init__(
        self,
        offline_after_failures: int = 3,
        recovered_after_successes: int = 2,
    ) -> None:
        self._offline_after_failures = offline_after_failures
        self._recovered_after_successes = recovered_after_successes
        self.current_state = ConnectivityState.ONLINE
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_successful_send: datetime | None = None

    def record_success(self) -> ConnectivityState:
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        self.last_successful_send = datetime.now(UTC)

        if self.current_state in (ConnectivityState.OFFLINE, ConnectivityState.DEGRADED):
            self.current_state = ConnectivityState.RECOVERING
        if (
            self.current_state == ConnectivityState.RECOVERING
            and self.consecutive_successes >= self._recovered_after_successes
        ) or self.current_state not in (
            ConnectivityState.RECOVERING,
            ConnectivityState.OFFLINE,
        ):
            self.current_state = ConnectivityState.ONLINE
        return self.current_state

    def record_failure(self) -> ConnectivityState:
        self.consecutive_successes = 0
        self.consecutive_failures += 1

        if self.consecutive_failures >= self._offline_after_failures:
            self.current_state = ConnectivityState.OFFLINE
        elif self.current_state != ConnectivityState.OFFLINE:
            self.current_state = ConnectivityState.DEGRADED
        return self.current_state

    @property
    def is_send_allowed(self) -> bool:
        """Sends are always attempted (never permanently blocked) — even OFFLINE keeps
        retrying with backoff, since a real edge must keep trying to reconnect."""
        return True
