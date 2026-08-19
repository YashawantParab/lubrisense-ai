"""Evaluation-only comparison of persisted `StateEstimate`s against a simulator
ground-truth proxy (Phase 12 brief §29). Reads plain ground-truth JSONL directly (no
`simulator` import — ground truth is just JSON on disk by the time a run has been
generated) and calls the pure metric functions in
`app.state_estimation.evaluation.metrics`. This script is intentionally NOT part of the
`app.state_estimation` package: production/online/replay code must never import anything
ground-truth-related, and keeping this script standalone makes that boundary structurally
obvious rather than merely documented (see docs/STATE_ESTIMATION.md "Evaluation
methodology").

Example:
  uv run python scripts/evaluate_state_estimation.py \
    --machine-id 88551bef-3149-5a8d-9645-bcd9502f4795 \
    --tenant-id bbdd114e-b5a7-5890-a5bd-9e8c787a5fe0 \
    --state-type LUBRICATION_DELIVERY_STATE \
    --ground-truth ../ml-service/data/ground_truth/restriction-1.jsonl \
    --start 2026-08-05T22:14:20+00:00 --end 2026-08-06T04:13:20+00:00
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.infrastructure.database import Database
from app.state_estimation.evaluation.metrics import (
    detection_lead_lag,
    mean_absolute_error,
    pearson_correlation,
    root_mean_squared_error,
    smoothness,
    trend_agreement_rate,
)
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _delivery_proxy(record: dict[str, Any]) -> float:
    circuits = record.get("circuits") or []
    pump_efficiency = record.get("pump_efficiency")
    values = [max(c["restriction_factor"], c["leakage_factor"]) for c in circuits]
    if pump_efficiency is not None:
        values.append(max(0.0, 1.0 - float(pump_efficiency)))
    return max(values) if values else 0.0


def _bearing_proxy(record: dict[str, Any]) -> float:
    bearings = record.get("bearings") or []
    healths = [float(b["health"]) for b in bearings]
    return 1.0 - min(healths) if healths else 0.0


_PROXY_FOR_STATE_TYPE = {
    "LUBRICATION_DELIVERY_STATE": _delivery_proxy,
    "BEARING_CONDITION_STATE": _bearing_proxy,
}


def _load_ground_truth(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    records.sort(key=lambda r: r["simulation_timestamp"])
    return records


def _nearest_proxy(records: list[dict[str, Any]], proxy_fn: Any, as_of: datetime) -> float:
    """Ground-truth-at-or-before `as_of`, matching how the estimator itself only ever sees
    evidence at or before its own `as_of_timestamp` (point-in-time correctness applied to
    the evaluation comparison too)."""
    best = None
    for record in records:
        ts = datetime.fromisoformat(record["simulation_timestamp"])
        if ts <= as_of:
            best = record
        else:
            break
    return proxy_fn(best) if best is not None else 0.0


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    proxy_fn = _PROXY_FOR_STATE_TYPE[args.state_type]
    ground_truth = _load_ground_truth(args.ground_truth)

    database = Database(get_settings())
    try:
        async with database.session() as session:
            repo = StateEstimateRepository(session)
            rows = await repo.list_for_machine(
                args.tenant_id,
                args.machine_id,
                state_type=args.state_type,
                start=args.start,
                end=args.end,
                limit=1000,
            )
    finally:
        await database.dispose()

    ordered = sorted(rows, key=lambda r: r.as_of_timestamp)
    if not ordered:
        return {"error": "no persisted state estimates found in this window"}

    estimated = [row.state_value for row in ordered]
    truth = [_nearest_proxy(ground_truth, proxy_fn, row.as_of_timestamp) for row in ordered]
    timestamps_seconds = [row.as_of_timestamp.timestamp() for row in ordered]

    truth_direction = []
    for i in range(len(truth)):
        if i == 0:
            truth_direction.append("STABLE")
            continue
        delta = truth[i] - truth[i - 1]
        truth_direction.append(
            "DETERIORATING" if delta > 1e-6 else "IMPROVING" if delta < -1e-6 else "STABLE"
        )
    estimated_trend = [row.trend.value for row in ordered]

    result: dict[str, Any] = {
        "sample_count": len(ordered),
        "mae": mean_absolute_error(estimated, truth),
        "rmse": root_mean_squared_error(estimated, truth),
        "pearson_correlation": pearson_correlation(estimated, truth),
        "trend_agreement_rate": trend_agreement_rate(estimated_trend, truth_direction),
        "prediction_only_fraction": sum(1 for r in ordered if r.prediction_only) / len(ordered),
    }
    if len(estimated) >= 2:
        result["smoothness"] = smoothness(estimated)
        lead_lag = detection_lead_lag(estimated, truth, timestamps_seconds, threshold=0.5)
        result["detection_lead_seconds"] = lead_lag.lead_seconds
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate state estimates against synthetic truth")
    parser.add_argument("--machine-id", required=True, type=uuid.UUID)
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--state-type", required=True, choices=sorted(_PROXY_FOR_STATE_TYPE))
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--start", required=True, type=_timestamp)
    parser.add_argument("--end", required=True, type=_timestamp)
    return parser


def main() -> None:
    args = _parser().parse_args()
    print(json.dumps(asyncio.run(_run(args)), indent=2, default=str))


if __name__ == "__main__":
    main()
