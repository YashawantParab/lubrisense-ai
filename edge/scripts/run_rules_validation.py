"""Live validation that the Phase 9 rules engine correctly reacts to real Phase 4 scenario
physics injected through the real Phase 5/6 pipeline (Phase 9 brief §35/§53), reusing
`run_scenario_validation.py`'s (Phase 7) exact harness: `SimulatorTelemetrySource` with an
injected `ScenarioInstance`, a real `EdgeRuntime`, real MQTT publish — zero changes to any
accepted Phase 4/5/6/7/8 source.

Requires the full docker-compose stack running with seeded demo data (`make seed`), and
must run where `mosquitto`/`postgres` hostnames resolve — i.e. inside the compose network:

    docker compose run --rm --entrypoint python edge scripts/run_rules_validation.py

Scope note (see docs/RULES_ENGINE.md "Verification scope"): the flagship's real registered
sensor set has no FLOW/PUMP_RUNTIME/CYCLE_COMPLETION sensor, so `gradual_restriction`
through the real chain cannot produce the specific FLOW_PRESSURE_RESTRICTION_PATTERN
(verified instead against a full synthetic topology in
`backend/tests/rules_engine/test_rule_engine.py`).

This script (run inside the `edge` container/image, which has the simulator/edge packages)
only injects the real scenario and confirms real telemetry landed via the real pipeline —
it prints `tenant_id|machine_id|window_start|window_end` on its last line. The rules
reprocess + finding checks run afterward from the host via `docker exec` against the
`backend` image instead (which owns `app.rules_engine`, not installed in the edge image) —
see `scripts/verify_rules_scenario.sh`, the wrapper that runs both halves in order.
"""

from __future__ import annotations

import os
import sys
import time

import psycopg
from simulator.engine.repository import TopologyRepository
from simulator.scenarios.definition import ProgressionSpec
from simulator.scenarios.instance import create_instance
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


def main() -> int:
    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    config = _build_config()
    topology = TopologyRepository(database_url=DATABASE_URL).load_machine_topology(
        asset_code=config.asset_code
    )
    machine_id = topology.id
    tenant_id = topology.tenant_id

    print(f"=== gradual_restriction on {config.asset_code} (machine_id={machine_id}) ===")

    definition = load_scenario_definition("gradual_restriction")
    instance = create_instance(
        definition,
        topology,
        progression_override=ProgressionSpec(type=ProgressionType.SIGMOID, onset_seconds=60.0),
    )

    source = SimulatorTelemetrySource(
        asset_code=config.asset_code,
        database_url=DATABASE_URL,
        step_seconds=3.0,
        scenario_instances=[instance],
    )
    transport = MqttTransport(
        broker_host=config.transport.broker_host,
        broker_port=config.transport.broker_port,
        topic_template=config.transport.topic_template,
        tenant_id=config.tenant_id,
        gateway_id=config.gateway_id,
        qos=config.transport.qos,
        client_id=f"{config.transport.client_id or 'edge'}-rules-validation",
    )
    runtime = EdgeRuntime(config, source, transport)
    run_started_wall_clock = time.time()
    runtime.start()
    try:
        runtime.run_ticks(50, sleep_between_seconds=0.05)
    finally:
        runtime.stop()
        source.close()

    print(f"  target circuit_id={instance.target_id}")

    # Give the real Phase 6 pipeline (MQTT -> bridge -> Kafka -> consumer) a moment to
    # persist the batch before querying.
    time.sleep(8.0)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM telemetry WHERE machine_id = %s "
            "AND source_timestamp >= to_timestamp(%s) AND measurement_type = 'PRESSURE'",
            (str(machine_id), run_started_wall_clock - 5.0),
        )
        pressure_row_count = cur.fetchone()[0]
    if pressure_row_count > 0:
        _pass(
            f"real scenario telemetry landed in TimescaleDB via the real pipeline "
            f"({pressure_row_count} PRESSURE rows)"
        )
    else:
        _fail("no PRESSURE telemetry landed for the scenario window — pipeline did not deliver")

    conn.close()

    scenario_start_iso = time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.gmtime(run_started_wall_clock - 5.0)
    )
    scenario_end_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time()))

    print("")
    if FAILURES == 0:
        print("run_rules_validation (edge half) PASSED: real scenario telemetry delivered.")
        print(f"RESULT|{tenant_id}|{machine_id}|{scenario_start_iso}|{scenario_end_iso}")
        return 0
    print(f"run_rules_validation FAILED: {FAILURES} check(s) failed — see above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
