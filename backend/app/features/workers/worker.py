"""Periodic latest-vector materializer with DB-backed readiness."""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.features.config.policy import FeaturePolicy, load_feature_policy
from app.features.definitions.sets import FEATURE_SETS
from app.features.materialization.materializer import FeatureMaterializer
from app.infrastructure.database import Database
from app.observability.metrics import WorkerMetrics
from app.observability.worker_health import WorkerHealthServer

logger = logging.getLogger("app.features.worker")


class FeatureWorker:
    def __init__(self, settings: Settings, policy: FeaturePolicy) -> None:
        self._settings = settings
        self._policy = policy
        self._database = Database(settings)
        self._metrics = WorkerMetrics()
        self._db_ready = False
        self._health_server = WorkerHealthServer(
            port=settings.feature_worker_health_port,
            service_name="feature-worker",
            readiness_check=self._readiness,
            metrics=self._metrics,
        )

    def _readiness(self) -> tuple[bool, dict[str, str]]:
        return self._db_ready, {"database": "reachable" if self._db_ready else "unreachable"}

    async def _run_cycle(self) -> None:
        started = datetime.now(UTC)
        async with self._database.session() as session:
            tracked = await SensorQualityStateRepository(session).list_all_tracked()
            machines: set[tuple[uuid.UUID, uuid.UUID]] = {
                (row.tenant_id, row.machine_id) for row in tracked if row.machine_id is not None
            }
            materializer = FeatureMaterializer(session, self._policy)
            vectors = failures = missing = suppressed = rows_scanned = 0
            max_lag = 0.0
            for tenant_id, machine_id in sorted(
                machines, key=lambda item: (str(item[0]), str(item[1]))
            ):
                for feature_set in FEATURE_SETS:
                    try:
                        async with session.begin_nested():
                            result = await materializer.materialize_latest(
                                tenant_id, machine_id, feature_set
                            )
                        vectors += int(result.inserted)
                        missing += result.features_missing
                        rows_scanned += result.telemetry_rows_scanned
                        lag = max(0.0, (started - result.vector.as_of_timestamp).total_seconds())
                        max_lag = max(max_lag, lag)
                        suppressed += int(
                            result.vector.quality_summary.get("suppressed_point_count", 0)
                        )
                    except Exception as exc:  # noqa: BLE001 - isolate one machine/set
                        failures += 1
                        logger.warning(
                            "feature materialization failed",
                            extra={
                                "machine_id": str(machine_id),
                                "feature_set": feature_set,
                                "error": str(exc),
                            },
                        )
            await session.commit()
        self._db_ready = True
        self._metrics.increment("feature_vectors_computed", vectors)
        self._metrics.increment("feature_computation_failures", failures)
        self._metrics.increment("features_missing", missing)
        self._metrics.increment("features_suppressed_quality", suppressed)
        self._metrics.set_gauge(
            "feature_computation_duration_seconds", (datetime.now(UTC) - started).total_seconds()
        )
        self._metrics.set_gauge("feature_materialization_lag_seconds", max_lag)
        self._metrics.set_gauge("feature_telemetry_rows_scanned", rows_scanned)

    async def run(self) -> None:
        self._db_ready = await self._database.check_connection()
        self._health_server.start()
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

        async def cycle_loop() -> None:
            while True:
                try:
                    await self._run_cycle()
                except Exception as exc:  # noqa: BLE001
                    self._db_ready = False
                    self._metrics.increment("feature_computation_failures")
                    logger.warning("feature worker cycle failed", extra={"error": str(exc)})
                await asyncio.sleep(self._settings.feature_worker_cycle_seconds)

        async def watchdog() -> None:
            while True:
                self._db_ready = await self._database.check_connection()
                await asyncio.sleep(5.0)

        tasks = [asyncio.create_task(cycle_loop()), asyncio.create_task(watchdog())]
        try:
            await stop.wait()
        finally:
            for task in tasks:
                task.cancel()
            await self._database.dispose()
            self._health_server.stop()


async def _main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-feature-worker",
    )
    await FeatureWorker(settings, load_feature_policy()).run()


if __name__ == "__main__":
    asyncio.run(_main())
