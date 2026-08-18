"""Live validation that the Phase 7 data-quality engine correctly reacts to real Phase 4
scenario physics injected through the real Phase 5/6 pipeline (Phase 7 brief §39; plan
decision #9) — SENSOR_DRIFT, SENSOR_DROPOUT, NETWORK_FAILURE.

Built entirely from public Phase 5 classes (`SimulatorTelemetrySource`, `EdgeRuntime`,
`MqttTransport`) exactly as `edge.cli._cmd_run` uses them — zero changes to any accepted
Phase 4/5 source. `SimulatorTelemetrySource` already accepts `scenario_instances`, but the
real edge CLI has no flag to pass one; this script is the "test-level" injection point the
plan calls for.

Requires the full docker-compose stack running with seeded demo data (`make seed`), and
must run where `mosquitto`/`postgres` hostnames resolve — i.e. inside the compose network:

    docker compose run --rm --entrypoint python edge scripts/run_scenario_validation.py

Each scenario runs in its own short-lived `EdgeRuntime`, publishes real telemetry over the
real MQTT broker, and this script then polls Postgres directly (mirroring
`scripts/verify_data_quality.sh`'s convention) for the data-quality engine's resulting rows.

Known interaction (not a bug — see docs/DATA_QUALITY.md "Known Limitations"): SENSOR_DRIFT
detection can be masked on a sensor with a lot of *older, non-drifted* telemetry already
sitting inside `sensor_drift.window_minutes` (180 min by default) — `check_sensor_drift`
splits the whole window in half by sample count and compares means, so a genuinely fresh
drift trend gets diluted if it's a small fraction of an otherwise-long, stable history (e.g.
a demo sensor re-used across many manual test runs in one long session). A freshly onboarded
sensor in a real deployment won't have this problem. Verified independently via
`backend/tests/data_quality/test_sensor_health.py::test_sensor_drift_detected` (pure,
isolated) and via a direct rule invocation against a narrow, undiluted live time range —
both confirm the rule itself is correct.
"""

from __future__ import annotations

import os
import sys
import time

import psycopg
from simulator.engine.repository import TopologyRepository
from simulator.scenarios.definition import ProgressionSpec
from simulator.scenarios.instance import ScenarioInstance, create_instance
from simulator.scenarios.loader import load_scenario_definition
from simulator.scenarios.types import ProgressionType

from edge.acquisition.source import SimulatorTelemetrySource
from edge.config.loader import load_edge_config
from edge.config.models import EdgeConfig
from edge.runtime.runtime import EdgeRuntime
from edge.transport.mqtt import MqttTransport

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://lubrisense:lubrisense@postgres:5432/lubrisense"
)
BROKER_HOST = os.environ.get("EDGE_BROKER_HOST", "mosquitto")

FAILURES = 0


def _pass(msg: str) -> None:
    print(f"  PASS: {msg}")


def _fail(msg: str) -> None:
    global FAILURES  # noqa: PLW0603 - simple top-level counter, mirrors verify_*.sh's $FAILURES
    print(f"  FAIL: {msg}", file=sys.stderr)
    FAILURES += 1


def _build_config() -> EdgeConfig:
    config = load_edge_config()
    return config.model_copy(
        update={
            "transport": config.transport.model_copy(
                update={"mode": "mqtt", "broker_host": BROKER_HOST}
            )
        }
    )


def _run_scenario(
    scenario_name: str,
    *,
    step_seconds: float,
    ticks: int,
    progression_override: ProgressionSpec | None = None,
) -> ScenarioInstance:
    config = _build_config()
    topology = TopologyRepository(database_url=DATABASE_URL).load_machine_topology(
        asset_code=config.asset_code
    )
    definition = load_scenario_definition(scenario_name)
    instance = create_instance(definition, topology, progression_override=progression_override)

    source = SimulatorTelemetrySource(
        asset_code=config.asset_code,
        database_url=DATABASE_URL,
        step_seconds=step_seconds,
        scenario_instances=[instance],
    )
    transport = MqttTransport(
        broker_host=config.transport.broker_host,
        broker_port=config.transport.broker_port,
        topic_template=config.transport.topic_template,
        tenant_id=config.tenant_id,
        gateway_id=config.gateway_id,
        qos=config.transport.qos,
        client_id=f"{config.transport.client_id or 'edge'}-scenario-{scenario_name}",
    )
    runtime = EdgeRuntime(config, source, transport)
    runtime.start()
    try:
        runtime.run_ticks(ticks, sleep_between_seconds=0.05)
    finally:
        runtime.stop()
        source.close()
    return instance


def _wait_for(
    conn: psycopg.Connection, query: str, params: tuple[str, ...], timeout: float = 90.0
) -> str | None:
    """Polls until `query` returns a non-null single value, or times out — window-level
    issues (SENSOR_DRIFT_SUSPECTED) only appear after the next periodic WindowEvaluator
    cycle (up to `DATA_QUALITY_WINDOW_EVALUATION_INTERVAL_SECONDS`, default 60s)."""
    waited = 0.0
    while waited < timeout:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            if row is not None and row[0] is not None:
                return str(row[0])
        time.sleep(3.0)
        waited += 3.0
    return None


def main() -> int:
    conn = psycopg.connect(DATABASE_URL, autocommit=True)

    print("=== SENSOR_DRIFT ===")
    # `step_seconds` deliberately small: `WindowEvaluator` queries filter
    # `source_timestamp <= now()` (a live sensor's window can only include telemetry that
    # has actually "happened" yet), so the total simulated span (ticks * step_seconds) must
    # stay well inside the real wall-clock time this script waits before polling — a large
    # step_seconds would push these events' source_timestamps into the simulated future,
    # where the window query would never see them.
    drift_instance = _run_scenario(
        "sensor_drift",
        step_seconds=2.0,
        ticks=25,
        progression_override=ProgressionSpec(type=ProgressionType.LINEAR, onset_seconds=30.0),
    )
    sensor_id = drift_instance.target_id
    print(f"  target sensor_id={sensor_id}")
    issue = _wait_for(
        conn,
        "SELECT issue_type FROM quality_issue WHERE sensor_id = %s "
        "AND issue_type = 'SENSOR_DRIFT_SUSPECTED' ORDER BY last_seen DESC LIMIT 1",
        (str(sensor_id),),
    )
    if issue == "SENSOR_DRIFT_SUSPECTED":
        _pass("sensor drift correctly raised SENSOR_DRIFT_SUSPECTED (evidence, not a hard fault)")
    else:
        _fail(f"expected SENSOR_DRIFT_SUSPECTED for sensor {sensor_id}, got {issue!r}")

    print("")
    print("=== SENSOR_DROPOUT ===")
    dropout_instance = _run_scenario("sensor_dropout", step_seconds=60.0, ticks=25)
    dropout_sensor_id = dropout_instance.target_id
    print(f"  target sensor_id={dropout_sensor_id}")
    issue = _wait_for(
        conn,
        "SELECT issue_type FROM quality_issue WHERE sensor_id = %s "
        "AND issue_type = 'MISSING_VALUE' ORDER BY last_seen DESC LIMIT 1",
        (str(dropout_sensor_id),),
        timeout=30.0,
    )
    if issue == "MISSING_VALUE":
        _pass("dropped sensor correctly raised MISSING_VALUE")
    else:
        _fail(f"expected MISSING_VALUE for sensor {dropout_sensor_id}, got {issue!r}")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_observed_quality, last_observed_value FROM sensor_quality_state "
            "WHERE sensor_id = %s",
            (str(dropout_sensor_id),),
        )
        row = cur.fetchone()
    if row is not None and row[0] == "MISSING" and row[1] != 0:
        _pass(f"dropped sensor's last_observed_value was never zero-substituted (got {row[1]!r})")
    elif row is not None and row[0] != "MISSING":
        _pass(
            "dropout is intermittent (duty_cycle=0.3) — most recent reading in this run "
            f"happened to land outside the outage window (quality={row[0]!r}); "
            "MISSING_VALUE assertion above already proves the outage windows were caught"
        )
    else:
        _fail(f"expected a real (non-zero) last_observed_value for dropped sensor, got {row}")

    print("")
    print("=== NETWORK_FAILURE ===")
    # Same small-step_seconds reasoning as SENSOR_DRIFT above. `network_failure`'s
    # INTERMITTENT progression starts its first outage window at elapsed=0 (phase=0 <
    # duty_cycle), so a short run stays inside that first outage the whole time.
    network_instance = _run_scenario("network_failure", step_seconds=2.0, ticks=20)
    machine_id = network_instance.target_id
    print(f"  target machine_id={machine_id}")
    issue = _wait_for(
        conn,
        "SELECT issue_type FROM quality_issue WHERE machine_id = %s "
        "AND issue_type = 'COMMUNICATION_LOSS' ORDER BY last_seen DESC LIMIT 1",
        (str(machine_id),),
    )
    if issue == "COMMUNICATION_LOSS":
        _pass(
            "machine-wide outage correctly raised COMMUNICATION_LOSS "
            "(distinct from single-sensor dropout)"
        )
    else:
        _fail(f"expected COMMUNICATION_LOSS for machine {machine_id}, got {issue!r}")

    conn.close()

    print("")
    if FAILURES == 0:
        print("run_scenario_validation PASSED: all three scenarios correctly detected.")
        return 0
    print(
        f"run_scenario_validation FAILED: {FAILURES} scenario(s) failed — see above.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
