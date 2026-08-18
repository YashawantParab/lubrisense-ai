"""Simulation runner CLI (Phase 3 brief §19-§21; extended Phase 4 §20-§21).

    python -m simulator run --asset-code L1-7B43-M000 --duration 24h --seed 42 \\
        --output data/conveyor_000_24h

    python -m simulator run --asset-code L1-7B43-M000 --duration 24h --seed 42 \\
        --scenario gradual_restriction --scenario-start 4h --severity 0.9 \\
        --output data/conveyor_000_gradual_restriction_24h

    python -m simulator run --asset-code L1-7B43-M000 --duration 24h --seed 42 \\
        --scenario-plan scenarios/multi_fault.yaml --output data/multi_fault_24h

Writes `<output>.readings.jsonl`, `<output>.ground_truth.jsonl`, and `<output>.meta.json`.
Historical generation (`--duration 7d`, `--duration 90d`, ...) uses exactly the same
`SimulationEngine` as a short smoke run — there is no separate "fake historical data"
code path (Phase 3 brief §20), scenario or otherwise.

`--scenario NAME` (repeatable) activates a failure mode using its YAML-defined defaults
(`simulator/config/scenarios/<name>.yaml`); `--scenario-start`/`--severity`/`--target`/
`--progression` override those defaults and, when more than one `--scenario` is given,
apply identically to all of them. For independent per-scenario overrides in a multi-fault
run, use `--scenario-plan <yaml>` instead — a list of scenario entries, each with its own
optional overrides — which takes priority over `--scenario` if both are given.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from simulator import __scenario_engine_version__, __version__
from simulator.config.loader import EngineeringConfig, load_engineering_config
from simulator.domain.topology import MachineTopology
from simulator.engine.logging_utils import get_simulator_logger, log_event
from simulator.engine.output import CsvReadingWriter, JsonlWriter, RunMetadata
from simulator.engine.repository import TopologyRepository
from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios import SCENARIO_CONFIG_VERSION
from simulator.scenarios.definition import ProgressionSpec
from simulator.scenarios.instance import ScenarioInstance, create_instance
from simulator.scenarios.loader import load_scenario_definition
from simulator.scenarios.scheduler import AutoRefillPolicy
from simulator.scenarios.types import ProgressionType

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([smhd])$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}

_MODE_DEFAULTS: dict[str, tuple[str, float]] = {
    # mode -> (default duration, default step_seconds)
    "SMOKE": ("5m", 5.0),
    "DEMO": ("4h", 5.0),
    "TRAINING": ("7d", 30.0),
    "FULL": ("90d", 60.0),
}


def parse_duration(value: str) -> float:
    match = _DURATION_RE.match(value.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f"Invalid duration {value!r}; expected e.g. '30s', '5m', '24h', '7d'"
        )
    amount, unit = match.groups()
    return float(amount) * _UNIT_SECONDS[unit.lower()]


@dataclass(frozen=True, slots=True)
class RunPlan:
    duration_seconds: float
    step_seconds: float
    estimated_rows: int


def plan_run(mode: str, duration: str | None, step: float | None, sensor_count: int) -> RunPlan:
    default_duration, default_step = _MODE_DEFAULTS[mode]
    duration_seconds = parse_duration(duration) if duration else parse_duration(default_duration)
    step_seconds = step if step is not None else default_step
    ticks = int(round(duration_seconds / step_seconds))
    estimated_rows = ticks * sensor_count
    return RunPlan(
        duration_seconds=duration_seconds, step_seconds=step_seconds, estimated_rows=estimated_rows
    )


def _build_scenario_instances(
    args: argparse.Namespace, topology: MachineTopology
) -> list[ScenarioInstance]:
    if args.scenario_plan:
        return _instances_from_plan(Path(args.scenario_plan), topology)
    return _instances_from_flags(args, topology)


def _instances_from_flags(
    args: argparse.Namespace, topology: MachineTopology
) -> list[ScenarioInstance]:
    names: list[str] = args.scenario or []
    progression_override = None
    if args.progression:
        progression_override = ProgressionSpec(type=ProgressionType(args.progression))

    instances = []
    for name in names:
        definition = load_scenario_definition(name)
        instances.append(
            create_instance(
                definition,
                topology,
                start_seconds=parse_duration(args.scenario_start) if args.scenario_start else None,
                severity_max=args.severity,
                target=args.target,
                progression_override=progression_override,
            )
        )
    return instances


def _instances_from_plan(path: Path, topology: MachineTopology) -> list[ScenarioInstance]:
    raw = yaml.safe_load(path.read_text())
    entries: list[dict[str, Any]] = raw.get("scenarios", [])
    instances = []
    for entry in entries:
        definition = load_scenario_definition(entry["scenario"])
        progression_override = None
        if "progression" in entry:
            progression_override = ProgressionSpec(
                type=ProgressionType(entry["progression"]),
                onset_seconds=entry.get("onset_seconds", definition.progression.onset_seconds),
                period_s=entry.get("period_s", definition.progression.period_s),
                duty_cycle=entry.get("duty_cycle", definition.progression.duty_cycle),
            )
        instances.append(
            create_instance(
                definition,
                topology,
                instance_id=entry.get("instance_id"),
                start_seconds=entry.get("start_seconds"),
                severity_max=entry.get("severity"),
                target=entry.get("target"),
                progression_override=progression_override,
            )
        )
    return instances


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m simulator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the simulator and write output files")
    asset_group = run_parser.add_mutually_exclusive_group(required=True)
    asset_group.add_argument("--asset-code", help="Machine asset_code from the seeded database")
    asset_group.add_argument("--asset-id", help="Machine id (UUID) from the seeded database")
    run_parser.add_argument(
        "--mode",
        choices=sorted(_MODE_DEFAULTS),
        default="DEMO",
        help="Data-volume preset controlling default duration/step (Phase 3 brief §21)",
    )
    run_parser.add_argument("--duration", help="e.g. '5m', '4h', '7d' (overrides --mode default)")
    run_parser.add_argument(
        "--step", type=float, help="Step size in seconds (overrides --mode default)"
    )
    run_parser.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed")
    run_parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="Only meaningful with --realtime: simulated-seconds per real-second",
    )
    run_parser.add_argument(
        "--realtime",
        action="store_true",
        help="Sleep between ticks to approximate real time (for a live demo); default is "
        "as-fast-as-possible offline generation",
    )
    run_parser.add_argument("--output", required=True, help="Output path prefix, e.g. data/run1")
    run_parser.add_argument("--csv", action="store_true", help="Also write a CSV copy of readings")
    run_parser.add_argument(
        "--yes", action="store_true", help="Skip the FULL-mode row-count confirmation"
    )
    run_parser.add_argument(
        "--config", type=Path, default=None, help="Path to an engineering config YAML"
    )
    run_parser.add_argument("--database-url", default=None, help="Overrides DATABASE_URL env var")

    run_parser.add_argument(
        "--scenario",
        action="append",
        help="Activate a failure mode by name (simulator/config/scenarios/<name>.yaml); "
        "repeatable for a multi-fault run",
    )
    run_parser.add_argument(
        "--scenario-start", help="e.g. '4h' — overrides every --scenario's default start time"
    )
    run_parser.add_argument(
        "--severity", type=float, help="0.0-1.0 — overrides every --scenario's max severity"
    )
    run_parser.add_argument(
        "--target", help="Entity code or UUID — overrides every --scenario's target"
    )
    run_parser.add_argument(
        "--progression",
        choices=[p.value for p in ProgressionType],
        help="Overrides every --scenario's progression type",
    )
    run_parser.add_argument(
        "--scenario-plan",
        help="Path to a YAML manifest of scenario entries for independent per-scenario "
        "overrides in a multi-fault run (takes priority over --scenario)",
    )

    run_parser.add_argument(
        "--refill-threshold",
        type=float,
        default=None,
        help="Reservoir level percent at/below which an automatic refill triggers "
        "(Phase 4 brief §24) — omit to disable auto-refill",
    )
    run_parser.add_argument("--refill-to", type=float, default=100.0, help="Refill target percent")
    run_parser.add_argument(
        "--refill-delay", default="0s", help="How long the level must stay below threshold first"
    )
    return parser


def run_command(args: argparse.Namespace) -> int:
    logger = get_simulator_logger()
    config: EngineeringConfig = load_engineering_config(args.config)

    repo = TopologyRepository(database_url=args.database_url)
    if args.asset_code:
        topology = repo.load_machine_topology(asset_code=args.asset_code)
    else:
        topology = repo.load_machine_topology(machine_id=uuid.UUID(args.asset_id))

    plan = plan_run(args.mode, args.duration, args.step, sensor_count=max(1, len(topology.sensors)))

    if args.mode == "FULL" and not args.yes:
        print(
            f"FULL mode estimated to write ~{plan.estimated_rows:,} telemetry rows "
            f"({plan.duration_seconds / 86400:.1f} simulated days at {plan.step_seconds}s step). "
            "Re-run with --yes to proceed.",
            file=sys.stderr,
        )
        return 1

    scenario_instances = _build_scenario_instances(args, topology)

    refill_policy = None
    if args.refill_threshold is not None:
        refill_policy = AutoRefillPolicy(
            threshold_percent=args.refill_threshold,
            to_percent=args.refill_to,
            delay_seconds=parse_duration(args.refill_delay),
        )

    run_id = str(uuid.uuid4())
    start_time = datetime.now(UTC)
    engine = SimulationEngine(
        topology=topology,
        config=config,
        seed=args.seed,
        start_time=start_time,
        step_seconds=plan.step_seconds,
        logger=logger,
        scenario_instances=scenario_instances,
        refill_policy=refill_policy,
    )

    output_prefix = Path(args.output)
    readings_path = output_prefix.with_suffix(".readings.jsonl")
    ground_truth_path = output_prefix.with_suffix(".ground_truth.jsonl")
    meta_path = output_prefix.with_suffix(".meta.json")

    meta = RunMetadata(
        run_id=run_id,
        simulator_version=__version__,
        scenario_engine_version=__scenario_engine_version__,
        engineering_config_version=config.config_version,
        scenario_config_version=SCENARIO_CONFIG_VERSION,
        seed=args.seed,
        tenant_id=topology.tenant_id,
        asset_id=topology.id,
        asset_code=topology.asset_code,
        start_timestamp=start_time,
        duration_seconds=plan.duration_seconds,
        step_seconds=plan.step_seconds,
        speed_multiplier=args.speed or 1.0,
        mode=args.mode,
        scenarios=tuple(i.definition.name for i in scenario_instances),
        readings_path=str(readings_path),
        ground_truth_path=str(ground_truth_path),
    )
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta.to_dict(), indent=2, default=str))

    csv_writer = CsvReadingWriter(output_prefix.with_suffix(".readings.csv")) if args.csv else None

    real_seconds_per_tick = (
        (plan.step_seconds / args.speed) if (args.realtime and args.speed) else 0.0
    )

    with JsonlWriter(readings_path) as readings_writer, JsonlWriter(ground_truth_path) as gt_writer:
        for tick in engine.run(plan.duration_seconds):
            for reading in tick.readings:
                readings_writer.write(reading)
                if csv_writer is not None:
                    csv_writer.write(reading)
            gt_writer.write(tick.ground_truth)
            if real_seconds_per_tick > 0:
                time.sleep(real_seconds_per_tick)

    if csv_writer is not None:
        csv_writer.close()

    log_event(
        logger,
        "run_complete",
        f"wrote {readings_writer.count} readings, {gt_writer.count} ground-truth records",
        readings=readings_writer.count,
        ground_truth=gt_writer.count,
        readings_path=str(readings_path),
        ground_truth_path=str(ground_truth_path),
    )
    print(f"Wrote {readings_writer.count} readings -> {readings_path}")
    print(f"Wrote {gt_writer.count} ground-truth records -> {ground_truth_path}")
    print(f"Run metadata -> {meta_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_command(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
