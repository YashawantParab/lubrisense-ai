from __future__ import annotations

import pytest

from edge.acquisition.source import FutureRealDeviceTelemetrySource, SimulatorTelemetrySource

pytestmark = pytest.mark.usefixtures("require_database")

FLAGSHIP_ASSET_CODE = "L1-7B43-M000"


def test_simulator_source_polls_real_topology() -> None:
    source = SimulatorTelemetrySource(asset_code=FLAGSHIP_ASSET_CODE, seed=1)
    assert source.sensor_count == 8
    observations = source.poll()
    assert len(observations) == 8
    measurement_types = {o.measurement_type for o in observations}
    assert "PRESSURE" in measurement_types
    assert "RESERVOIR_LEVEL" in measurement_types
    source.close()


def test_simulator_source_never_exposes_true_value_field() -> None:
    """`RawObservation` structurally has no `true_value` field — this asserts that boundary
    directly rather than trusting the dataclass definition alone."""
    source = SimulatorTelemetrySource(asset_code=FLAGSHIP_ASSET_CODE, seed=1)
    observations = source.poll()
    for obs in observations:
        assert not hasattr(obs, "true_value")
    source.close()


def test_future_real_device_source_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        FutureRealDeviceTelemetrySource()
