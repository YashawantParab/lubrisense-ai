"""Rules worker (Phase 9 brief §28/§30/§46/§47): `python -m app.rules_engine.workers.worker`.

Not a Kafka consumer — like `app.baselines.workers.worker` (Phase 8), the rules engine
reads already-persisted `telemetry`/`sensor_quality_state`/`BaselineProfile` directly rather
than reacting to individual events: a finding is a judgment over a window of evidence, not a
single-event decision, and every rule already depends on Phase 8 baselines that are
themselves only refreshed periodically — evaluating on every raw telemetry event would race
ahead of the baselines the rules need. A periodic asyncio loop is the right shape instead
(default cycle interval `RULES_WORKER_CYCLE_SECONDS`), matching ADR (rules-worker-not-a-
kafka-consumer).

Each cycle: discover every currently-tracked machine from `sensor_quality_state` (the same
cross-tenant discovery pattern `app.data_quality.worker`/`app.baselines.workers.worker` use
— grouped by machine, not iterated per sensor), evaluate each with
`RuleEngine.evaluate_machine`, per-machine `SAVEPOINT` isolation so one bad machine never
blocks the cycle (matching Phase 7/8's worker precedent).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from datetime import UTC, datetime

from app.baselines.config.policy import BaselinePolicy, load_baseline_policy
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.infrastructure.database import Database
from app.observability.metrics import WorkerMetrics
from app.observability.worker_health import WorkerHealthServer
from app.rules_engine.config.policy import RulesPolicy, load_rules_policy
from app.rules_engine.services.rule_engine import RuleEngine

logger = logging.getLogger("app.rules_engine.worker")

_DB_WATCHDOG_INTERVAL_SECONDS = 5.0


class RulesWorker:
    def __init__(
        self, settings: Settings, baseline_policy: BaselinePolicy, rules_policy: RulesPolicy
    ) -> None:
        self._settings = settings
        self._baseline_policy = baseline_policy
        self._rules_policy = rules_policy
        self._metrics = WorkerMetrics()
        self._database = Database(settings)
        self._db_ready = False
        self._health_server = WorkerHealthServer(
            port=settings.rules_worker_health_port,
            service_name="rules-worker",
            readiness_check=self._readiness,
            metrics=self._metrics,
        )

    def _readiness(self) -> tuple[bool, dict[str, str]]:
        details = {"database": "reachable" if self._db_ready else "unreachable"}
        return self._db_ready, details

    async def _run_cycle(self) -> None:
        started = datetime.now(UTC)
        async with self._database.session() as session:
            state_repo = SensorQualityStateRepository(session)
            engine = RuleEngine(session, self._baseline_policy, self._rules_policy)

            tracked = await state_repo.list_all_tracked()
            machines: set[tuple[uuid.UUID, uuid.UUID]] = {
                (row.tenant_id, row.machine_id) for row in tracked if row.machine_id is not None
            }

            evaluated = errors = created = updated = resolved = signals_total = 0
            for tenant_id, machine_id in machines:
                try:
                    async with session.begin_nested():
                        result = await engine.evaluate_machine(tenant_id, machine_id, started)
                    evaluated += 1
                    created += result.findings_created
                    updated += result.findings_updated
                    resolved += result.findings_resolved
                    signals_total += result.signals_evaluated
                    errors += result.findings_errors
                except Exception as exc:  # noqa: BLE001 - per-machine isolation, see module docstring
                    errors += 1
                    logger.warning(
                        "rule evaluation failed for one machine, skipping",
                        extra={"machine_id": str(machine_id), "error": str(exc)},
                    )

            await session.commit()

        self._db_ready = True
        duration = (datetime.now(UTC) - started).total_seconds()
        self._metrics.increment("rules_evaluated", evaluated)
        self._metrics.increment("rule_findings_created", created)
        self._metrics.increment("rule_findings_active", updated)
        self._metrics.increment("rule_findings_resolved", resolved)
        self._metrics.increment("rule_processing_errors", errors)
        self._metrics.set_gauge("rule_processing_duration_seconds", duration)
        self._metrics.set_gauge("rules_signals_evaluated", signals_total)
        self._metrics.set_gauge("rules_tracked_machines", len(machines))
        logger.info(
            "rules cycle complete",
            extra={
                "machines_evaluated": evaluated,
                "findings_created": created,
                "findings_updated": updated,
                "findings_resolved": resolved,
                "errors": errors,
                "duration_seconds": duration,
            },
        )

    async def _cycle_loop(self) -> None:
        while True:
            try:
                await self._run_cycle()
            except Exception as exc:  # noqa: BLE001 - never let one bad cycle kill the loop
                self._db_ready = False
                logger.warning("rules cycle failed", extra={"error": str(exc)})
            await asyncio.sleep(self._settings.rules_worker_cycle_seconds)

    async def _db_watchdog_loop(self) -> None:
        while True:
            self._db_ready = await self._database.check_connection()
            await asyncio.sleep(_DB_WATCHDOG_INTERVAL_SECONDS)

    async def run(self) -> None:
        self._db_ready = await self._database.check_connection()
        self._health_server.start()

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

        cycle_task = asyncio.create_task(self._cycle_loop())
        watchdog_task = asyncio.create_task(self._db_watchdog_loop())
        try:
            await stop_event.wait()
        finally:
            logger.info("rules worker shutting down")
            cycle_task.cancel()
            watchdog_task.cancel()
            await self._database.dispose()
            self._health_server.stop()


async def _main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-rules-worker",
    )
    baseline_policy = load_baseline_policy()
    rules_policy = load_rules_policy()
    worker = RulesWorker(settings, baseline_policy, rules_policy)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
