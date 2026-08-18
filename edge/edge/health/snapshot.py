"""`EdgeHealth` — a point-in-time status snapshot, built on demand from the buffer +
connectivity manager + rule engine + config (Phase 5 brief §23)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from edge.connectivity.manager import ConnectivityManager
from edge.health.metrics import EdgeMetrics


@dataclass(slots=True)
class EdgeHealth:
    runtime_status: str
    gateway_id: str
    connected_sensor_count: int
    last_acquisition_time: datetime | None
    buffer_depth: int
    oldest_buffered_event_age_seconds: float | None
    connectivity_state: str
    last_transport_success: datetime | None
    open_local_alert_count: int
    config_version: str
    firmware_version: str
    metrics: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime_status": self.runtime_status,
            "gateway_id": self.gateway_id,
            "connected_sensor_count": self.connected_sensor_count,
            "last_acquisition_time": self.last_acquisition_time.isoformat()
            if self.last_acquisition_time
            else None,
            "buffer_depth": self.buffer_depth,
            "oldest_buffered_event_age_seconds": self.oldest_buffered_event_age_seconds,
            "connectivity_state": self.connectivity_state,
            "last_transport_success": self.last_transport_success.isoformat()
            if self.last_transport_success
            else None,
            "open_local_alert_count": self.open_local_alert_count,
            "config_version": self.config_version,
            "firmware_version": self.firmware_version,
            "metrics": self.metrics,
        }


def build_health_snapshot(
    *,
    runtime_status: str,
    gateway_id: str,
    connected_sensor_count: int,
    last_acquisition_time: datetime | None,
    buffer_depth: int,
    oldest_buffered_event_age_seconds: float | None,
    connectivity: ConnectivityManager,
    open_local_alert_count: int,
    config_version: str,
    firmware_version: str,
    metrics: EdgeMetrics,
) -> EdgeHealth:
    return EdgeHealth(
        runtime_status=runtime_status,
        gateway_id=gateway_id,
        connected_sensor_count=connected_sensor_count,
        last_acquisition_time=last_acquisition_time,
        buffer_depth=buffer_depth,
        oldest_buffered_event_age_seconds=oldest_buffered_event_age_seconds,
        connectivity_state=connectivity.current_state.value,
        last_transport_success=connectivity.last_successful_send,
        open_local_alert_count=open_local_alert_count,
        config_version=config_version,
        firmware_version=firmware_version,
        metrics=metrics.to_dict(),
    )
