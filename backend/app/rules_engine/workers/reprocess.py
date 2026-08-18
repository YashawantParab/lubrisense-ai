"""Historical rule reprocessing CLI (Phase 9 brief §31/§45):

    python -m app.rules_engine.workers.reprocess \\
        --machine-id ... --start 2026-08-01T00:00:00 --end 2026-08-02T00:00:00

Runs `RuleEngine.evaluate_machine` once against the exact given range (via
`window_override`) — the same engine method the live worker uses (brief §30's "prefer
consuming telemetry/quality/baseline-ready data in a clean way", mirroring
`app.baselines.workers.backfill`'s "one method, two callers" shape). Never deletes prior
findings (brief §31) — a reprocess run participates in the same CANDIDATE/ACTIVE/RECOVERING/
RESOLVED lifecycle as a live cycle, so it can only ever advance or resolve a finding through
the normal debounce/hysteresis path, never overwrite history.

Without `--machine-id`, reprocesses every machine currently tracked in
`sensor_quality_state` for the tenant.
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from datetime import datetime

from app.baselines.config.policy import load_baseline_policy
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.infrastructure.database import Database
from app.rules_engine.config.policy import load_rules_policy
from app.rules_engine.services.rule_engine import RuleEngine


async def reprocess(
    tenant_id: uuid.UUID, machine_id: uuid.UUID | None, start: datetime, end: datetime
) -> dict[str, int | float]:
    settings = get_settings()
    baseline_policy = load_baseline_policy()
    rules_policy = load_rules_policy()
    database = Database(settings)
    started = time.monotonic()
    machines_processed = findings_created = findings_updated = findings_resolved = 0
    try:
        async with database.session() as session:
            engine = RuleEngine(session, baseline_policy, rules_policy)

            machine_ids: set[uuid.UUID] = set()
            if machine_id is not None:
                machine_ids.add(machine_id)
            else:
                state_repo = SensorQualityStateRepository(session)
                tracked = await state_repo.list_for_tenant(tenant_id, limit=2000)
                machine_ids = {row.machine_id for row in tracked if row.machine_id is not None}

            for one_machine_id in machine_ids:
                result = await engine.evaluate_machine(
                    tenant_id, one_machine_id, end, window_override=(start, end)
                )
                machines_processed += 1
                findings_created += result.findings_created
                findings_updated += result.findings_updated
                findings_resolved += result.findings_resolved

            await session.commit()
    finally:
        await database.dispose()

    elapsed = time.monotonic() - started
    return {
        "machines_processed": machines_processed,
        "findings_created": findings_created,
        "findings_updated": findings_updated,
        "findings_resolved": findings_resolved,
        "elapsed_seconds": elapsed,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Historical rule-finding reprocessing")
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--machine-id", required=False, type=uuid.UUID, default=None)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-rules-reprocess",
    )
    summary = asyncio.run(reprocess(args.tenant_id, args.machine_id, args.start, args.end))
    print(
        f"reprocessed {summary['machines_processed']} machine(s): "
        f"{summary['findings_created']} created, {summary['findings_updated']} updated, "
        f"{summary['findings_resolved']} resolved in {summary['elapsed_seconds']:.2f}s"
    )


if __name__ == "__main__":
    main()
