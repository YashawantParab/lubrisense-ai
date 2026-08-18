from __future__ import annotations

from edge.runtime.runtime import EdgeRuntime
from edge.transport.test_transport import RecordingTestTransport
from tests.fakes import FakeTelemetrySource, healthy_tick


def test_health_snapshot_reflects_state(edge_config) -> None:  # type: ignore[no-untyped-def]
    source = FakeTelemetrySource([healthy_tick(0)])
    transport = RecordingTestTransport()
    runtime = EdgeRuntime(edge_config, source, transport)
    runtime.acquire_once()

    snapshot = runtime.health_snapshot()
    assert snapshot.gateway_id == edge_config.gateway_id
    assert snapshot.buffer_depth == 3
    assert snapshot.config_version == edge_config.config_version
    assert snapshot.firmware_version == edge_config.firmware_version
    assert snapshot.metrics["acquired"] == 3
    assert snapshot.metrics["buffered"] == 3
    as_dict = snapshot.to_dict()
    assert as_dict["gateway_id"] == edge_config.gateway_id
    runtime.stop()


def test_config_version_change_is_recorded(edge_config) -> None:  # type: ignore[no-untyped-def]
    source = FakeTelemetrySource([])
    transport = RecordingTestTransport()
    runtime = EdgeRuntime(edge_config, source, transport)
    assert runtime.metrics.config_changes == 1  # first time this gateway_id is seen
    runtime.stop()

    same_version_source = FakeTelemetrySource([])
    same_version_transport = RecordingTestTransport()
    again = EdgeRuntime(edge_config, same_version_source, same_version_transport)
    assert again.metrics.config_changes == 0  # unchanged version, no new event
    again.stop()

    bumped = edge_config.model_copy(update={"config_version": "2"})
    bumped_source = FakeTelemetrySource([])
    bumped_transport = RecordingTestTransport()
    changed = EdgeRuntime(bumped, bumped_source, bumped_transport)
    assert changed.metrics.config_changes == 1
    changed.stop()
