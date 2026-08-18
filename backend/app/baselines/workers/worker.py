"""Baseline worker (Phase 8 brief §28/§29/§46/§47): `python -m app.baselines.workers.worker`.

Not a Kafka consumer — unlike the Phase 6 telemetry consumer / Phase 7 data-quality
worker, the baseline engine reads already-persisted `telemetry` (plus Phase 7's
`sensor_quality_state`) directly rather than reacting to individual events (brief §6: "do
not re-run the simulator", and there is no per-event baseline decision to make — a
baseline is a statistic over a window, not a single-event judgment). A periodic asyncio
loop is therefore the right shape, not a second consumer group (TECHNICAL_DECISIONS.md,
baseline-worker-not-a-kafka-consumer ADR).

Each cycle: discover every currently-tracked sensor from `sensor_quality_state`
(cross-tenant, mirroring `app.data_quality.worker`'s own discovery pattern), skip any sensor
whose measurement-type-specific `refresh_interval_seconds` hasn't elapsed yet (brief §29 —
"do not schedule every profile identically"), refresh it, then refresh cycle-level baselines
once per machine seen, then sweep for staleness. Per-sensor/per-machine failures are isolated
with a `SAVEPOINT`, matching Phase 7's worker precedent — one bad sensor never blocks the
cycle.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
import uuid
from datetime import UTC, datetime

from app.baselines.config.policy import BaselinePolicy, load_baseline_policy
from app.baselines.repositories.baseline_profile_repository import BaselineProfileRepository
from app.baselines.services.baseline_engine import BaselineEngine
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import BaselineState, BaselineStrategyType
from app.domain.models import Sensor
from app.infrastructure.database import Database
from app.observability.metrics import WorkerMetrics
from app.observability.worker_health import WorkerHealthServer
from app.repositories.sensor import SensorRepository

logger = logging.getLogger("app.baselines.worker")


class BaselineWorker:
    def __init__(self, settings: Settings, policy: BaselinePolicy) -> None:
        self._settings = settings
        self._policy = policy
        self._metrics = WorkerMetrics()
        self._database = Database(settings)
        self._db_ready = False
        self._health_server = WorkerHealthServer(
            port=settings.baseline_worker_health_port,
            service_name="baseline-worker",
            readiness_check=self._readiness,
            metrics=self._metrics,
        )

    def _readiness(self) -> tuple[bool, dict[str, str]]:
        details = {"database": "reachable" if self._db_ready else "unreachable"}
        return self._db_ready, details

    async def _run_cycle(self) -> None:
        started = time.monotonic()
        now = datetime.now(UTC)
        evaluated = failures = 0
        async with self._database.session() as session:
            quality_repo = SensorQualityStateRepository(session)
            sensor_repo = SensorRepository(session)
            profile_repo = BaselineProfileRepository(session)
            engine = BaselineEngine(session, self._policy)

            tracked = await quality_repo.list_all_tracked()
            machines_seen: set[tuple[uuid.UUID, uuid.UUID]] = set()

            for row in tracked:
                sensor = await sensor_repo.get(row.tenant_id, row.sensor_id)
                if sensor is None:
                    continue
                if not await self._is_due(profile_repo, row.tenant_id, sensor, now):
                    continue
                try:
                    async with session.begin_nested():
                        await engine.refresh_sensor(row.tenant_id, sensor, now)
                    evaluated += 1
                except Exception as exc:  # noqa: BLE001 - per-sensor isolation
                    failures += 1
                    logger.warning(
                        "baseline refresh failed for one sensor, skipping",
                        extra={"sensor_id": str(row.sensor_id), "error": str(exc)},
                    )
                if row.machine_id is not None:
                    machines_seen.add((row.tenant_id, row.machine_id))

            for tenant_id, machine_id in machines_seen:
                try:
                    async with session.begin_nested():
                        await engine.refresh_machine_cycle(tenant_id, machine_id, now)
                except Exception as exc:  # noqa: BLE001 - per-machine isolation
                    failures += 1
                    logger.warning(
                        "cycle-baseline refresh failed for one machine, skipping",
                        extra={"machine_id": str(machine_id), "error": str(exc)},
                    )

            stale_marked = await self._sweep_staleness(profile_repo, now)
            state_counts = await self._current_state_counts(profile_repo)
            await session.commit()

        self._db_ready = True
        self._metrics.increment("baseline_events_processed", evaluated)
        self._metrics.increment("baseline_build_failures", failures)
        self._metrics.increment("baseline_stale_profiles", stale_marked)
        self._metrics.set_gauge("baseline_build_duration_seconds", time.monotonic() - started)
        for state, count in state_counts.items():
            self._metrics.set_gauge(f"baseline_profiles_{state.lower()}", count)
        logger.info(
            "baseline cycle complete",
            extra={
                "evaluated": evaluated,
                "failures": failures,
                "machines": len(machines_seen),
                "stale_marked": stale_marked,
            },
        )

    async def _is_due(
        self,
        profile_repo: BaselineProfileRepository,
        tenant_id: uuid.UUID,
        sensor: Sensor,
        now: datetime,
    ) -> bool:
        current = await profile_repo.get_current(
            tenant_id, sensor.id, BaselineStrategyType.ROLLING_ASSET_BASELINE, ""
        )
        if current is None or current.last_evaluated_at is None:
            return True
        interval = self._policy.refresh_interval_seconds_for(sensor.sensor_type.value)
        return (now - current.last_evaluated_at).total_seconds() >= interval

    async def _sweep_staleness(self, profile_repo: BaselineProfileRepository, now: datetime) -> int:
        marked = 0
        for profile in await profile_repo.list_all_current():
            if profile.state != BaselineState.ACTIVE or profile.last_evaluated_at is None:
                continue
            if (now - profile.last_evaluated_at).total_seconds() > profile.stale_after_seconds:
                await profile_repo.mark_stale(profile.id)
                marked += 1
        return marked

    async def _current_state_counts(
        self, profile_repo: BaselineProfileRepository
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for profile in await profile_repo.list_all_current():
            counts[profile.state.value] = counts.get(profile.state.value, 0) + 1
        return counts

    async def _cycle_loop(self) -> None:
        while True:
            try:
                await self._run_cycle()
            except Exception as exc:  # noqa: BLE001 - never let one bad cycle kill the loop
                self._db_ready = False
                logger.warning("baseline cycle failed", extra={"error": str(exc)})
            await asyncio.sleep(self._settings.baseline_refresh_interval_seconds)

    async def run(self) -> None:
        self._db_ready = await self._database.check_connection()
        self._health_server.start()

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

        cycle_task = asyncio.create_task(self._cycle_loop())
        try:
            await stop_event.wait()
        finally:
            logger.info("baseline worker shutting down")
            cycle_task.cancel()
            await self._database.dispose()
            self._health_server.stop()


async def _main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-baseline-worker",
    )
    policy = load_baseline_policy()
    worker = BaselineWorker(settings, policy)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
