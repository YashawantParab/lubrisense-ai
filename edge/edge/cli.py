"""Edge controller CLI (Phase 5 brief §34):

python -m edge run --gateway GW-RIDGE-CRUSH --asset-code L1-7B43-M000 --transport noop
python -m edge status --gateway GW-RIDGE-CRUSH
python -m edge buffer list --gateway GW-RIDGE-CRUSH --status pending
python -m edge replay --gateway GW-RIDGE-CRUSH
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edge.acquisition.source import SimulatorTelemetrySource
from edge.buffering.store import LocalBuffer
from edge.config.loader import load_edge_config
from edge.config.models import EdgeConfig
from edge.domain.enums import BufferStatus
from edge.runtime.gateway_lock import GatewayLock, GatewayLockHeldError
from edge.runtime.runtime import EdgeRuntime
from edge.transport.base import EdgeTransport
from edge.transport.mqtt import MqttTransport
from edge.transport.noop import NoopTransport
from edge.transport.test_transport import RecordingTestTransport


def _load_config(args: argparse.Namespace) -> EdgeConfig:
    config = load_edge_config(Path(args.config) if args.config else None)
    overrides: dict[str, object] = {}
    if getattr(args, "gateway", None):
        overrides["gateway_code"] = args.gateway
    if getattr(args, "asset_code", None):
        overrides["asset_code"] = args.asset_code
    if overrides:
        config = config.model_copy(update=overrides)
    return config


def _build_transport(config: EdgeConfig, mode_override: str | None) -> EdgeTransport:
    mode = mode_override or config.transport.mode
    if mode == "noop":
        return NoopTransport()
    if mode == "test":
        return RecordingTestTransport()
    if mode == "mqtt":
        return MqttTransport(
            broker_host=config.transport.broker_host,
            broker_port=config.transport.broker_port,
            topic_template=config.transport.topic_template,
            tenant_id=config.tenant_id,
            gateway_id=config.gateway_id,
            qos=config.transport.qos,
            client_id=config.transport.client_id,
        )
    raise ValueError(f"unknown transport mode {mode!r}")


def _cmd_run(args: argparse.Namespace) -> int:
    config = _load_config(args)
    lock = GatewayLock(config.resolved_db_path(), config.gateway_id)
    try:
        lock.acquire()
    except GatewayLockHeldError as exc:
        print(f"run FAILED: {exc}", file=sys.stderr)
        return 1

    try:
        source = SimulatorTelemetrySource(asset_code=config.asset_code, seed=args.seed)
        transport = _build_transport(config, args.transport)
        runtime = EdgeRuntime(config, source, transport)
        runtime.start()
        snapshot = None
        try:
            runtime.run_ticks(args.ticks, sleep_between_seconds=args.interval or 0.0)
            snapshot = runtime.health_snapshot()
        finally:
            runtime.stop()
            source.close()
        print(json.dumps(snapshot.to_dict(), indent=2))
        return 0
    finally:
        lock.release()


def _cmd_status(args: argparse.Namespace) -> int:
    config = _load_config(args)
    buffer = LocalBuffer(config.resolved_db_path())
    try:
        status = {
            "gateway_id": config.gateway_id,
            "config_version": config.config_version,
            "buffer_depth_pending": buffer.pending_count(),
            "oldest_pending_age_seconds": buffer.oldest_pending_age_seconds(),
            "counts_by_status": buffer.counts_by_status(),
        }
        print(json.dumps(status, indent=2))
        return 0
    finally:
        buffer.close()


def _cmd_buffer_list(args: argparse.Namespace) -> int:
    config = _load_config(args)
    buffer = LocalBuffer(config.resolved_db_path())
    try:
        status = BufferStatus(args.status.upper()) if args.status else None
        rows = buffer.list_events(status=status, limit=args.limit)
        print(json.dumps(rows, indent=2))
        return 0
    finally:
        buffer.close()


def _cmd_replay(args: argparse.Namespace) -> int:
    config = _load_config(args)
    buffer = LocalBuffer(config.resolved_db_path())
    try:
        source = SimulatorTelemetrySource(asset_code=config.asset_code, seed=args.seed)
        transport = _build_transport(config, args.transport)
        runtime = EdgeRuntime(config, source, transport, buffer=buffer)
        sent = runtime.replay_now()
        print(json.dumps({"replayed": sent}, indent=2))
        return 0
    finally:
        source.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m edge")
    sub = parser.add_subparsers(dest="command", required=True)

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", default=None, help="Path to an edge config YAML")
        p.add_argument("--gateway", default=None, help="Overrides config gateway_code")

    run_p = sub.add_parser("run", help="Run the edge controller")
    _common(run_p)
    run_p.add_argument("--asset-code", default=None, help="Overrides config asset_code")
    run_p.add_argument("--transport", choices=["noop", "test", "mqtt"], default=None)
    run_p.add_argument("--ticks", type=int, default=10, help="Number of acquisition ticks to run")
    run_p.add_argument("--interval", type=float, default=0.0, help="Sleep seconds between ticks")
    run_p.add_argument("--seed", type=int, default=42)
    run_p.set_defaults(func=_cmd_run)

    status_p = sub.add_parser("status", help="Print edge health/status")
    _common(status_p)
    status_p.set_defaults(func=_cmd_status)

    buffer_p = sub.add_parser("buffer", help="Inspect the local buffer")
    buffer_sub = buffer_p.add_subparsers(dest="buffer_command", required=True)
    list_p = buffer_sub.add_parser("list", help="List buffered events")
    _common(list_p)
    list_p.add_argument("--status", default=None, help="Filter by status (pending/sent/...)")
    list_p.add_argument("--limit", type=int, default=100)
    list_p.set_defaults(func=_cmd_buffer_list)

    replay_p = sub.add_parser("replay", help="Manually trigger a synchronous replay pass")
    _common(replay_p)
    replay_p.add_argument("--transport", choices=["noop", "test", "mqtt"], default=None)
    replay_p.add_argument("--seed", type=int, default=42)
    replay_p.set_defaults(func=_cmd_replay)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
