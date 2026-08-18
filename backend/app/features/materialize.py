"""Deterministic historical materialization CLI.

Example:
  python -m app.features.materialize --machine-id UUID \
    --feature-set LUBRICATION_ANOMALY_V1 --start ISO8601 --end ISO8601
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.domain.models import Machine
from app.features.config.policy import load_feature_policy
from app.features.definitions.sets import FEATURE_SETS
from app.features.materialization.materializer import FeatureMaterializer
from app.infrastructure.database import Database


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize point-in-time feature vectors")
    parser.add_argument("--machine-id", required=True, type=uuid.UUID)
    parser.add_argument("--tenant-id", type=uuid.UUID)
    parser.add_argument("--feature-set", required=True, choices=sorted(FEATURE_SETS))
    parser.add_argument("--start", required=True, type=_timestamp)
    parser.add_argument("--end", required=True, type=_timestamp)
    parser.add_argument("--interval-seconds", type=int, default=900)
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.start > args.end:
        raise ValueError("start must be <= end")
    if args.interval_seconds <= 0:
        raise ValueError("interval-seconds must be positive")
    database = Database(get_settings())
    started = datetime.now(UTC)
    try:
        async with database.session() as session:
            tenant_id = args.tenant_id
            if tenant_id is None:
                tenant_id = await session.scalar(
                    select(Machine.tenant_id).where(Machine.id == args.machine_id)
                )
            if tenant_id is None:
                raise ValueError("machine not found")
            materializer = FeatureMaterializer(session, load_feature_policy())
            current = args.start
            vectors = inserted = rows = features = 0
            while current <= args.end:
                result = await materializer.materialize(
                    tenant_id, args.machine_id, args.feature_set, current
                )
                vectors += 1
                inserted += int(result.inserted)
                rows += result.telemetry_rows_scanned
                features += result.features_generated
                current += timedelta(seconds=args.interval_seconds)
            await session.commit()
        duration = (datetime.now(UTC) - started).total_seconds()
        return {
            "machines": 1,
            "timestamps_requested": vectors,
            "vectors_inserted": inserted,
            "telemetry_rows_scanned": rows,
            "features_generated": features,
            "duration_seconds": duration,
        }
    finally:
        await database.dispose()


def main() -> None:
    args = _parser().parse_args()
    print(json.dumps(asyncio.run(_run(args)), sort_keys=True))


if __name__ == "__main__":
    main()
