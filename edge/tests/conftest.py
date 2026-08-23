from __future__ import annotations

import shutil
import socket
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from edge.config.models import EdgeConfig

FLAGSHIP_ASSET_CODE = "L1-7B43-M000"  # "Ore Transfer Conveyor CV-101" — seeded Phase 2 demo tenant
FLAGSHIP_TENANT_ID = "bbdd114e-b5a7-5890-a5bd-9e8c787a5fe0"
FLAGSHIP_GATEWAY_CODE = "GW-RIDGE-CRUSH"


def _mqtt_broker_available(host: str = "localhost", port: int = 1883) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _database_available() -> bool:
    try:
        from simulator.engine.repository import TopologyRepository

        TopologyRepository().load_machine_topology(asset_code=FLAGSHIP_ASSET_CODE)
        return True
    except Exception:  # noqa: BLE001 — environment probe, not app logic
        return False


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    return str(tmp_path / "edge_buffer.db")


@pytest.fixture
def edge_config(tmp_db_path: str) -> EdgeConfig:
    gateway_id = str(uuid.uuid4())
    return EdgeConfig.model_validate(
        {
            "config_version": "1",
            "gateway_id": gateway_id,
            "gateway_code": FLAGSHIP_GATEWAY_CODE,
            "tenant_id": FLAGSHIP_TENANT_ID,
            "asset_code": FLAGSHIP_ASSET_CODE,
            "poll_interval_seconds": 1.0,
            "buffer": {
                "db_path": tmp_db_path,
                "max_buffered_events": 1000,
                "max_buffer_age_seconds": 3600,
            },
            "transport": {"mode": "test"},
        }
    )


@pytest.fixture
def require_database() -> None:
    if not _database_available():
        pytest.skip("live database unavailable (docker compose stack not reachable)")


@pytest.fixture
def require_mqtt() -> None:
    if not _mqtt_broker_available():
        pytest.skip("MQTT broker unavailable at localhost:1883")
    if shutil.which("docker") is None:
        pytest.skip("docker CLI unavailable — required to simulate a broker outage")


@pytest.fixture
def mosquitto_guaranteed_running() -> Iterator[None]:
    """Ensures the shared dev-stack `lubrisense-mosquitto` container is left running after
    the test, regardless of outcome — this is a shared container, not a test-owned one."""
    yield
    subprocess.run(
        ["docker", "compose", "start", "mosquitto"],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
    )
    _wait_for_mqtt()


def _wait_for_mqtt(timeout: float = 30.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _mqtt_broker_available():
            return
        time.sleep(0.5)
