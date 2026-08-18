"""Small Phase 5 reference run: flagship conveyor healthy -> real mosquitto outage ->
recovery. Captures buffer-depth trend and event counts to a compact JSON summary (not raw
logs) at `edge/data/reference_run_summary.json`.

Usage (from `edge/`, docker compose stack running):

    uv run python scripts/reference_run.py
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path

from edge.acquisition.source import SimulatorTelemetrySource
from edge.config.models import EdgeConfig
from edge.runtime.runtime import EdgeRuntime
from edge.transport.mqtt import MqttTransport

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "reference_run_summary.json"


def _docker_compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=REPO_ROOT, check=True, capture_output=True)


def main() -> None:
    db_path = f"/tmp/edge_reference_run_{uuid.uuid4().hex[:8]}.db"
    config = EdgeConfig.model_validate(
        {
            "config_version": "1",
            "gateway_id": str(uuid.uuid4()),
            "gateway_code": "GW-RIDGE-CRUSH",
            "tenant_id": "bbdd114e-b5a7-5890-a5bd-9e8c787a5fe0",
            "asset_code": "L1-7B43-M000",
            "poll_interval_seconds": 0.2,
            "buffer": {
                "db_path": db_path,
                "max_buffered_events": 10000,
                "max_buffer_age_seconds": 3600,
            },
            "transport": {"mode": "mqtt", "broker_host": "localhost", "broker_port": 1883},
        }
    )

    source = SimulatorTelemetrySource(asset_code=config.asset_code, seed=99)
    transport = MqttTransport(
        broker_host=config.transport.broker_host,
        broker_port=config.transport.broker_port,
        topic_template=config.transport.topic_template,
        tenant_id=config.tenant_id,
        gateway_id=config.gateway_id,
        qos=config.transport.qos,
    )
    runtime = EdgeRuntime(config, source, transport)
    runtime.start()

    trend: list[dict[str, object]] = []

    def snapshot(label: str) -> None:
        trend.append(
            {
                "label": label,
                "t": round(time.monotonic() - t0, 2),
                "buffer_depth": runtime.buffer.pending_count(),
                "connectivity_state": runtime.connectivity.current_state.value,
                "metrics": runtime.metrics.to_dict(),
            }
        )

    t0 = time.monotonic()
    try:
        runtime.run_ticks(5, sleep_between_seconds=0.2)
        time.sleep(1.0)
        snapshot("healthy")

        _docker_compose("stop", "mosquitto")
        time.sleep(1.0)
        runtime.run_ticks(10, sleep_between_seconds=0.2)
        time.sleep(1.0)
        snapshot("outage")

        _docker_compose("start", "mosquitto")
        deadline = time.monotonic() + 30.0
        while runtime.buffer.pending_count() > 0 and time.monotonic() < deadline:
            time.sleep(0.5)
        snapshot("recovered")
    finally:
        runtime.stop()
        source.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"gateway_id": config.gateway_id, "trend": trend}, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
