"""Historical state-estimation replay CLI (Phase 12 brief §19).

Example:
  python -m app.state_estimation.replay --machine-id UUID \
    --start ISO8601 --end ISO8601
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.domain.models import Machine
from app.infrastructure.database import Database
from app.state_estimation.services.replay_service import ReplayService


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay state estimation over a time window")
    parser.add_argument("--machine-id", required=True, type=uuid.UUID)
    parser.add_argument("--tenant-id", type=uuid.UUID)
    parser.add_argument("--start", required=True, type=_timestamp)
    parser.add_argument("--end", required=True, type=_timestamp)
    parser.add_argument("--limit", type=int, default=1000)
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.start > args.end:
        raise ValueError("start must be <= end")
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
            service = ReplayService(session)
            counts = await service.replay_machine(
                tenant_id, args.machine_id, args.start, args.end, limit=args.limit
            )
            await session.commit()
        duration = (datetime.now(UTC) - started).total_seconds()
        return {"estimates_inserted": counts, "duration_seconds": duration}
    finally:
        await database.dispose()


def main() -> None:
    args = _parser().parse_args()
    print(json.dumps(asyncio.run(_run(args)), sort_keys=True))


if __name__ == "__main__":
    main()
