"""Phase 11 ML training-data generation (Phase 11 brief §45-§47).

Drives real simulator scenario runs through the real Phase 5/6 pipeline — the same
`SimulatorTelemetrySource` + `EdgeRuntime` + real MQTT publish harness Phase 7/9's
`run_scenario_validation.py`/`run_rules_validation.py` already use — across a deliberately
varied set of scenario types, seeds, onset timings, and (for the generalization test) a
second real equipped asset. Real telemetry lands in the real TimescaleDB `telemetry` table
via the real MQTT bridge/Kafka consumer; the always-on data-quality/baseline/rules workers
then process it exactly as they do for any other telemetry.

This script's own responsibility ends at telemetry delivery + capturing ground truth. Phase
10 feature-vector materialization (`python -m app.features.materialize`, run separately from
`backend/`) and `ml_service.datasets.builder.DatasetBuilder` (which joins materialized
feature vectors with this script's ground-truth JSONL for labels) come after.

Ground truth is captured locally, in-process, directly from `SimulationEngine.step()` —
never round-tripped through the wire/DB — and written to its own JSONL stream, structurally
separate from telemetry (mirrors `simulator.engine.output`'s own ground-truth-vs-readings
separation). `ml_service` reads this file only to derive labels, never as a feature source.

Run from the repo root, against the live Docker Compose stack (host-published ports):

    cd edge && uv run python ../edge/scripts/generate_ml_training_data.py \
        --output-dir ../ml-service/data

Requires: `docker compose up` (postgres, mosquitto, mqtt-bridge, telemetry-consumer, ...)
already running and `make seed` already applied (both true in the working demo environment
Phase 11 was validated against).
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from simulator.config.loader import load_engineering_config
from simulator.engine.output import JsonlWriter
from simulator.engine.repository import TopologyRepository
from simulator.engine.simulation_engine import SimulationEngine, SimulationTick
from simulator.scenarios.definition import ProgressionSpec
from simulator.scenarios.instance import ScenarioInstance, create_instance
from simulator.scenarios.loader import load_scenario_definition

from edge.acquisition.source import RawObservation
from edge.config.loader import load_edge_config
from edge.config.models import EdgeConfig
from edge.runtime.runtime import EdgeRuntime
from edge.transport.mqtt import MqttTransport

DEFAULT_DATABASE_URL = "postgresql://lubrisense:lubrisense@localhost:5432/lubrisense"
DEFAULT_BROKER_HOST = "localhost"
STEP_SECONDS = 60.0
DURATION_TICKS = 360  # 6 simulated hours per run
COMPRESSED_ONSET_SECONDS = 5400.0  # 1.5 simulated hours — fits within the 6h run window

# Each run gets its own non-overlapping simulated time slot (Phase 11 brief §8's
# point-in-time correctness depends on this): `SimulatorTelemetrySource` otherwise anchors
# every run at real wall-clock "now", so two runs on the SAME machine started minutes apart
# would produce telemetry claiming to occupy the SAME simulated time window — corrupting
# feature computation, which would silently blend multiple scenario runs' readings into one
# window. `RUN_SLOT_HOURS` (> one run's own 6h duration, with margin) guarantees every
# flagship-machine run's [start, end) is disjoint from every other's.
RUN_SLOT_HOURS = 8.0


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    name: str
    target: str | None = None
    onset_seconds: float | None = COMPRESSED_ONSET_SECONDS


@dataclass(frozen=True, slots=True)
class RunSpec:
    run_tag: str
    asset_code: str
    gateway_code: str
    seed: int
    scenarios: tuple[ScenarioSpec, ...] = ()

    @property
    def is_healthy(self) -> bool:
        return not self.scenarios


# Flagship (8 sensors, no FLOW/PUMP_RUNTIME/CYCLE_COMPLETION — the real heterogeneous-
# instrumentation case, Phase 11 brief §32) plus one second equipped asset held out
# entirely for the asset-generalization test (§31).
FLAGSHIP_ASSET = "L1-7B43-M000"
FLAGSHIP_GATEWAY = "GW-RIDGE-CRUSH"
SECOND_ASSET = "L1-5F44-M020"
SECOND_GATEWAY = "GW-DORN-BULK"

RUN_SPECS: tuple[RunSpec, ...] = (
    # Healthy — diverse seeds for noise variety (Phase 11 brief §46).
    RunSpec("healthy-1", FLAGSHIP_ASSET, FLAGSHIP_GATEWAY, seed=1),
    RunSpec("healthy-2", FLAGSHIP_ASSET, FLAGSHIP_GATEWAY, seed=2),
    RunSpec("healthy-3", FLAGSHIP_ASSET, FLAGSHIP_GATEWAY, seed=3),
    RunSpec("healthy-4", FLAGSHIP_ASSET, FLAGSHIP_GATEWAY, seed=4),
    # Gradual restriction — two seeds, two onset timings.
    RunSpec(
        "restriction-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=10,
        scenarios=(ScenarioSpec("gradual_restriction", onset_seconds=4500.0),),
    ),
    RunSpec(
        "restriction-2",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=11,
        scenarios=(ScenarioSpec("gradual_restriction", onset_seconds=6300.0),),
    ),
    # Sudden blockage (STEP — no onset compression needed).
    RunSpec(
        "blockage-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=20,
        scenarios=(ScenarioSpec("sudden_blockage", onset_seconds=None),),
    ),
    RunSpec(
        "blockage-2",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=21,
        scenarios=(ScenarioSpec("sudden_blockage", onset_seconds=None),),
    ),
    # Leakage.
    RunSpec(
        "leakage-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=30,
        scenarios=(ScenarioSpec("leakage", onset_seconds=4500.0),),
    ),
    RunSpec(
        "leakage-2",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=31,
        scenarios=(ScenarioSpec("leakage", onset_seconds=6300.0),),
    ),
    # Pump degradation.
    RunSpec(
        "pump-degradation-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=40,
        scenarios=(ScenarioSpec("pump_degradation", onset_seconds=4500.0),),
    ),
    RunSpec(
        "pump-degradation-2",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=41,
        scenarios=(ScenarioSpec("pump_degradation", onset_seconds=6300.0),),
    ),
    # Sensor drift / dropout -> SENSOR_FAULT.
    RunSpec(
        "sensor-drift-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=50,
        scenarios=(ScenarioSpec("sensor_drift", onset_seconds=4500.0),),
    ),
    RunSpec(
        "sensor-drift-2",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=51,
        scenarios=(ScenarioSpec("sensor_drift", onset_seconds=6300.0),),
    ),
    RunSpec(
        "sensor-dropout-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=60,
        scenarios=(ScenarioSpec("sensor_dropout", onset_seconds=None),),
    ),
    RunSpec(
        "sensor-dropout-2",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=61,
        scenarios=(ScenarioSpec("sensor_dropout", onset_seconds=None),),
    ),
    # Independent bearing fault.
    RunSpec(
        "bearing-fault-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=70,
        scenarios=(ScenarioSpec("independent_bearing_fault", onset_seconds=4500.0),),
    ),
    RunSpec(
        "bearing-fault-2",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=71,
        scenarios=(ScenarioSpec("independent_bearing_fault", onset_seconds=6300.0),),
    ),
    # Out-of-schema (-> UNKNOWN, Phase 11 brief §10-§11).
    RunSpec(
        "over-lubrication-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=80,
        scenarios=(ScenarioSpec("over_lubrication", onset_seconds=2700.0),),
    ),
    RunSpec(
        "low-reservoir-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=90,
        scenarios=(ScenarioSpec("low_reservoir", onset_seconds=None),),
    ),
    # Network failure — excluded from supervised labels (data-quality state, not an
    # equipment label); used for anomaly/robustness evaluation only.
    RunSpec(
        "network-failure-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=100,
        scenarios=(ScenarioSpec("network_failure", onset_seconds=None),),
    ),
    # Multi-fault (Phase 11 brief §55) — restriction + independent bearing fault together.
    RunSpec(
        "multi-fault-1",
        FLAGSHIP_ASSET,
        FLAGSHIP_GATEWAY,
        seed=200,
        scenarios=(
            ScenarioSpec("gradual_restriction", onset_seconds=4500.0),
            ScenarioSpec("independent_bearing_fault", onset_seconds=4500.0),
        ),
    ),
    # Second asset — held out entirely from the flagship's runs, for asset generalization
    # (Phase 11 brief §31).
    RunSpec("healthy-second-asset-1", SECOND_ASSET, SECOND_GATEWAY, seed=300),
    RunSpec(
        "restriction-second-asset-1",
        SECOND_ASSET,
        SECOND_GATEWAY,
        seed=301,
        scenarios=(ScenarioSpec("gradual_restriction", onset_seconds=4500.0),),
    ),
)


class GroundTruthCapturingSource:
    """A `TelemetrySource` matching `edge.acquisition.source.SimulatorTelemetrySource`'s own
    `poll()`/`close()` contract exactly, plus capturing each tick's `GroundTruthRecord` to a
    local JSONL sink. Built directly against `SimulationEngine` (not by subclassing
    `SimulatorTelemetrySource`) for the one thing that class does not expose: an explicit
    `start_time`, required so concurrent scenario runs on the same machine occupy disjoint
    simulated time windows (see `RUN_SLOT_HOURS` above) — everything else is byte-identical
    to the real Phase 5 edge acquisition adapter."""

    def __init__(
        self,
        asset_code: str,
        seed: int,
        step_seconds: float,
        database_url: str,
        start_time: datetime,
        scenario_instances: list[ScenarioInstance],
        ground_truth_sink: JsonlWriter,
    ) -> None:
        engineering_config = load_engineering_config()
        topology = TopologyRepository(database_url=database_url).load_machine_topology(
            asset_code=asset_code
        )
        self._engine = SimulationEngine(
            topology=topology,
            config=engineering_config,
            seed=seed,
            start_time=start_time,
            step_seconds=step_seconds,
            scenario_instances=scenario_instances,
        )
        self._sink = ground_truth_sink

    def close(self) -> None:
        pass

    def poll(self) -> list[RawObservation]:
        tick: SimulationTick = self._engine.step()
        self._sink.write(tick.ground_truth)
        return [
            RawObservation(
                source_timestamp=r.simulation_timestamp,
                tenant_id=r.tenant_id,
                machine_id=r.asset_id,
                component_id=r.component_id,
                sensor_id=r.sensor_id,
                measurement_type=r.measurement_type,
                value=r.observed_value,
                unit=r.unit,
                quality=r.quality,
                operating_state=r.operating_state,
            )
            for r in tick.readings
        ]


def _build_scenario_instances(
    specs: tuple[ScenarioSpec, ...], topology: object
) -> list[ScenarioInstance]:
    instances = []
    for spec in specs:
        definition = load_scenario_definition(spec.name)
        override = None
        if spec.onset_seconds is not None:
            override = ProgressionSpec(
                type=definition.progression.type,
                onset_seconds=spec.onset_seconds,
                period_s=definition.progression.period_s,
                duty_cycle=definition.progression.duty_cycle,
                sigmoid_steepness=definition.progression.sigmoid_steepness,
            )
        instances.append(
            create_instance(
                definition,
                topology,  # type: ignore[arg-type]
                start_seconds=0.0,
                progression_override=override,
            )
        )
    return instances


def _build_edge_config(
    spec: RunSpec, tenant_id: str, gateway_id: str, broker_host: str, tmp_dir: Path
) -> EdgeConfig:
    base = load_edge_config()
    return base.model_copy(
        update={
            "gateway_id": gateway_id,
            "gateway_code": spec.gateway_code,
            "tenant_id": tenant_id,
            "asset_code": spec.asset_code,
            "buffer": base.buffer.model_copy(
                # Shared per-gateway, NOT per-run: EnvelopeBuilder persists a monotonic
                # (gateway_id, sensor_id) sequence in this buffer (ADR-044). A per-run
                # buffer path would reset that sequence to 0 for every run sharing a real
                # gateway identity, causing deterministic event_id collisions
                # (uuid5(gateway_id, sensor_id, sequence_number), ADR-045) across
                # completely unrelated runs — a real bug caught during this phase's own
                # live verification (see TECHNICAL_DECISIONS.md ADR-099).
                update={"db_path": str(tmp_dir / "{gateway_id}.db")}
            ),
            "transport": base.transport.model_copy(
                update={
                    "mode": "mqtt",
                    "broker_host": broker_host,
                    "client_id": f"ml-gen-{spec.run_tag}",
                }
            ),
        }
    )


def _resolve_identity(
    conn: psycopg.Connection, asset_code: str, gateway_code: str
) -> tuple[str, str, str]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, tenant_id FROM machine WHERE asset_code = %s", (asset_code,))
        machine_row = cur.fetchone()
        if machine_row is None:
            raise SystemExit(f"asset_code {asset_code!r} not found — is demo data seeded?")
        cur.execute("SELECT id FROM gateway WHERE gateway_code = %s", (gateway_code,))
        gateway_row = cur.fetchone()
        if gateway_row is None:
            raise SystemExit(f"gateway_code {gateway_code!r} not found — is demo data seeded?")
    return str(machine_row["tenant_id"]), str(machine_row["id"]), str(gateway_row["id"])


#: Anchor for every run's disjoint simulated time slot — a fixed point safely in the past
#: (so no run's telemetry ever claims a future `source_timestamp`) and recent enough that it
#: does not exercise any untested extreme-age code path in staleness/quality logic.
_SLOT_BASE = datetime.now(UTC) - timedelta(days=14)


def run_one(
    spec: RunSpec,
    *,
    slot_index: int,
    database_url: str,
    broker_host: str,
    output_dir: Path,
    tmp_dir: Path,
) -> dict[str, object]:
    conn = psycopg.connect(database_url, autocommit=True)
    tenant_id, machine_id, gateway_id = _resolve_identity(conn, spec.asset_code, spec.gateway_code)
    conn.close()

    config = _build_edge_config(spec, tenant_id, gateway_id, broker_host, tmp_dir)
    topology = TopologyRepository(database_url=database_url).load_machine_topology(
        asset_code=spec.asset_code
    )
    scenario_instances = _build_scenario_instances(spec.scenarios, topology)
    start_time = _SLOT_BASE + timedelta(hours=RUN_SLOT_HOURS * slot_index)

    ground_truth_path = output_dir / "ground_truth" / f"{spec.run_tag}.jsonl"
    ground_truth_path.parent.mkdir(parents=True, exist_ok=True)
    sink = JsonlWriter(ground_truth_path)

    source = GroundTruthCapturingSource(
        asset_code=spec.asset_code,
        seed=spec.seed,
        step_seconds=STEP_SECONDS,
        database_url=database_url,
        start_time=start_time,
        scenario_instances=scenario_instances,
        ground_truth_sink=sink,
    )
    transport = MqttTransport(
        broker_host=config.transport.broker_host,
        broker_port=config.transport.broker_port,
        topic_template=config.transport.topic_template,
        tenant_id=config.tenant_id,
        gateway_id=config.gateway_id,
        qos=config.transport.qos,
        client_id=config.transport.client_id or f"ml-gen-{spec.run_tag}",
    )
    runtime = EdgeRuntime(config, source, transport)

    start_wall = time.time()
    run_started_at = datetime.now(UTC)
    runtime.start()
    try:
        runtime.run_ticks(DURATION_TICKS, sleep_between_seconds=0.0)
        drain_deadline = time.monotonic() + 180.0
        while runtime.health_snapshot().buffer_depth > 0 and time.monotonic() < drain_deadline:
            time.sleep(0.2)
        remaining = runtime.health_snapshot().buffer_depth
        if remaining:
            print(f"  WARNING: {spec.run_tag} buffer did not fully drain ({remaining} pending)")
    finally:
        runtime.stop()
        source.close()
        sink.close()

    elapsed = time.time() - start_wall
    print(
        f"  {spec.run_tag}: {DURATION_TICKS} ticks, {sink.count} ground-truth records, "
        f"{elapsed:.1f}s wall time"
    )

    end_timestamp_iso = None
    with ground_truth_path.open(encoding="utf-8") as fh:
        lines = fh.readlines()
        if lines:
            first = json.loads(lines[0])
            last = json.loads(lines[-1])
            start_timestamp_iso = first["simulation_timestamp"]
            end_timestamp_iso = last["simulation_timestamp"]
        else:
            start_timestamp_iso = run_started_at.isoformat()
            end_timestamp_iso = run_started_at.isoformat()

    manifest = {
        "run_id": spec.run_tag,
        "tenant_id": tenant_id,
        "machine_id": machine_id,
        "asset_code": spec.asset_code,
        "seed": spec.seed,
        "scenario_types": [s.name.upper() for s in spec.scenarios],
        "start_timestamp": start_timestamp_iso,
        "end_timestamp": end_timestamp_iso,
        "ground_truth_path": str(ground_truth_path.resolve()),
        "is_healthy": spec.is_healthy,
    }
    manifest_dir = output_dir / "runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / f"{spec.run_tag}.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 11 ML training data.")
    parser.add_argument("--output-dir", type=Path, default=Path("../ml-service/data"))
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--broker-host", default=DEFAULT_BROKER_HOST)
    parser.add_argument("--only", nargs="*", default=None, help="run_tag subset to (re)generate")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    tmp_dir = Path("/tmp/lubrisense-ml-gen")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    specs = RUN_SPECS
    if args.only:
        wanted = set(args.only)
        specs = tuple(s for s in RUN_SPECS if s.run_tag in wanted)
        if not specs:
            raise SystemExit(f"no run specs matched --only {args.only}")

    print(f"Generating {len(specs)} run(s) into {output_dir}")
    manifests = []
    for spec in specs:
        slot_index = RUN_SPECS.index(spec)
        manifests.append(
            run_one(
                spec,
                slot_index=slot_index,
                database_url=args.database_url,
                broker_host=args.broker_host,
                output_dir=output_dir,
                tmp_dir=tmp_dir,
            )
        )

    print(f"Done. {len(manifests)} run manifests written under {output_dir / 'runs'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
