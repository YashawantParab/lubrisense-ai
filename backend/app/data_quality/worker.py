"""Kafka -> data-quality-engine worker (Phase 7 brief §6/§30; plan decisions #2/#3).

Runs two concurrent loops in one process:

- **event-level loop**: an independent Kafka consumer group
  (`settings.data_quality_consumer_group_id`, default `lubrisense-data-quality`) reading the
  *same* `lubrisense.telemetry.v1` topic Phase 6's `telemetry-consumer` reads — fan-out, not
  a post-persistence trigger. Runs `QualityEngine.process_event` per structurally-valid,
  enrichable event.
- **window-level loop**: a periodic asyncio task (interval
  `settings.data_quality_window_evaluation_interval_seconds`) that re-evaluates every
  currently-tracked sensor and machine via `WindowEvaluator`, using a fresh time-range query
  each cycle — no in-memory rolling state to lose on restart.

Failure handling deliberately diverges from Phase 6's consumer (plan decision #3): a
**batch-level** transient failure (DB unreachable) retries with backoff and never commits
offsets, same as Phase 6 — this worker must never silently skip a batch of events. But a
**per-event** rule/persistence exception is isolated with a `SAVEPOINT`
(`session.begin_nested()`), caught, logged, and counted
(`quality_processing_errors`) — the batch still commits. Rationale: this worker is
secondary/advisory analysis, not the system of record (Phase 6's consumer already is), and
must never be allowed to stall real telemetry visibility over one bad rule evaluation on one
event; it is fully recoverable via `reprocess.py`.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from datetime import datetime

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from aiokafka.errors import KafkaError

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.data_quality.config.policy import QualityPolicy, load_quality_policy
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.data_quality.services.quality_engine import QualityEngine
from app.data_quality.services.window_evaluator import WindowEvaluator
from app.infrastructure.database import Database
from app.observability.metrics import WorkerMetrics
from app.observability.worker_health import WorkerHealthServer
from app.pipeline.backoff import compute_backoff
from app.pipeline.enrichment import ContextEnrichmentService, EnrichmentFailure
from app.pipeline.validation import SchemaValidator, ValidationFailure
from app.repositories.sensor import SensorRepository

logger = logging.getLogger("app.data_quality.worker")

_KAFKA_START_MAX_BACKOFF_SECONDS = 30.0
_DB_WATCHDOG_INTERVAL_SECONDS = 5.0


def _parse_header_timestamp(headers: dict[str, bytes], key: str) -> datetime | None:
    raw = headers.get(key)
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw.decode("utf-8"))
    except ValueError:
        return None


class DataQualityWorker:
    def __init__(self, settings: Settings, policy: QualityPolicy) -> None:
        self._settings = settings
        self._policy = policy
        self._metrics = WorkerMetrics()
        self._validator = SchemaValidator(settings.pipeline_supported_schema_versions_set)
        self._database = Database(settings)

        self._consumer: AIOKafkaConsumer | None = None
        self._kafka_ready = False
        self._db_ready = False

        self._health_server = WorkerHealthServer(
            port=settings.data_quality_worker_health_port,
            service_name="data-quality-worker",
            readiness_check=self._readiness,
            metrics=self._metrics,
        )

    def _readiness(self) -> tuple[bool, dict[str, str]]:
        details = {
            "kafka": "connected" if self._kafka_ready else "disconnected",
            "database": "reachable" if self._db_ready else "unreachable",
        }
        return self._kafka_ready and self._db_ready, details

    # -- event-level loop ------------------------------------------------------------------

    async def _topic_loop(self) -> None:
        assert self._consumer is not None  # noqa: S101 - set by run() before this task starts
        while True:
            try:
                batches = await self._consumer.getmany(
                    timeout_ms=int(self._settings.pipeline_batch_timeout_seconds * 1000),
                    max_records=self._settings.pipeline_batch_size,
                )
                self._kafka_ready = True
            except KafkaError as exc:
                self._kafka_ready = False
                logger.warning("Kafka fetch failed", extra={"error": str(exc)})
                await asyncio.sleep(2.0)
                continue

            records = [rec for recs in batches.values() for rec in recs]
            if not records:
                continue
            await self._process_batch(records)

    async def _process_batch(self, records: list[ConsumerRecord]) -> None:
        assert self._consumer is not None  # noqa: S101
        attempt = 0
        while True:
            try:
                processed = skipped = errors = 0
                async with self._database.session() as session:
                    engine = QualityEngine(session, self._policy)
                    enricher = ContextEnrichmentService(session)
                    sensor_repo = SensorRepository(session)

                    for rec in records:
                        result = self._validator.validate(rec.value)
                        if isinstance(result, ValidationFailure):
                            skipped += 1
                            continue
                        enriched = await enricher.enrich(result)
                        if isinstance(enriched, EnrichmentFailure):
                            # Not accepted into `telemetry` either (Phase 6 quarantines
                            # it) — nothing valid to assess quality for.
                            skipped += 1
                            continue
                        sensor = await sensor_repo.get(result.tenant_id, result.sensor_id)
                        if sensor is None:
                            skipped += 1
                            continue

                        headers = dict(rec.headers or ())
                        mqtt_received_timestamp = (
                            _parse_header_timestamp(headers, "mqtt_received_timestamp")
                            or result.edge_received_timestamp
                        )
                        try:
                            async with session.begin_nested():
                                await engine.process_event(
                                    result, enriched, sensor, mqtt_received_timestamp
                                )
                            processed += 1
                        except Exception as exc:  # noqa: BLE001 - per-event isolation, see module docstring
                            errors += 1
                            logger.warning(
                                "quality rule evaluation failed for one event, skipping",
                                extra={"event_id": str(result.event_id), "error": str(exc)},
                            )

                    await session.commit()

                self._db_ready = True
                self._metrics.increment("quality_events_processed", processed)
                self._metrics.increment("quality_events_skipped", skipped)
                self._metrics.increment("quality_processing_errors", errors)
                self._metrics.increment("kafka_consumer_messages", len(records))
                self._metrics.set_gauge("batch_size", len(records))

                await self._consumer.commit()
                return
            except Exception as exc:  # noqa: BLE001 - batch-level retry boundary, see module docstring
                self._db_ready = False
                logger.warning(
                    "data-quality batch failed, retrying without advancing offsets",
                    extra={"attempt": attempt, "batch_size": len(records), "error": str(exc)},
                )
                await asyncio.sleep(
                    compute_backoff(
                        attempt, max_delay_seconds=self._settings.pipeline_retry_max_backoff_seconds
                    )
                )
                attempt += 1

    # -- window-level loop ------------------------------------------------------------------

    async def _window_evaluation_loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.data_quality_window_evaluation_interval_seconds)
            try:
                await self._run_window_evaluation_cycle()
            except Exception as exc:  # noqa: BLE001 - never let one bad cycle kill the loop
                logger.warning("window evaluation cycle failed", extra={"error": str(exc)})

    async def _run_window_evaluation_cycle(self) -> None:
        async with self._database.session() as session:
            evaluator = WindowEvaluator(session, self._policy)
            state_repo = SensorQualityStateRepository(session)
            sensor_repo = SensorRepository(session)

            tracked = await state_repo.list_all_tracked()
            machines_seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
            evaluated = errors = 0

            for row in tracked:
                sensor = await sensor_repo.get(row.tenant_id, row.sensor_id)
                if sensor is None:
                    continue
                try:
                    async with session.begin_nested():
                        await evaluator.evaluate_sensor(
                            row.tenant_id, row.sensor_id, row.machine_id, sensor.sensor_type.value
                        )
                    evaluated += 1
                except Exception as exc:  # noqa: BLE001 - per-sensor isolation
                    errors += 1
                    logger.warning(
                        "window evaluation failed for one sensor, skipping",
                        extra={"sensor_id": str(row.sensor_id), "error": str(exc)},
                    )
                if row.machine_id is not None:
                    machines_seen.add((row.tenant_id, row.machine_id))

            for tenant_id, machine_id in machines_seen:
                try:
                    async with session.begin_nested():
                        await evaluator.evaluate_machine_communication(tenant_id, machine_id)
                except Exception as exc:  # noqa: BLE001 - per-machine isolation
                    errors += 1
                    logger.warning(
                        "communication-loss evaluation failed for one machine, skipping",
                        extra={"machine_id": str(machine_id), "error": str(exc)},
                    )

            await session.commit()

        self._db_ready = True
        self._metrics.increment("quality_window_evaluations", evaluated)
        self._metrics.increment("quality_window_evaluation_errors", errors)
        self._metrics.set_gauge("quality_tracked_sensors", len(tracked))

    # -- watchdogs / lifecycle ---------------------------------------------------------------

    async def _db_watchdog_loop(self) -> None:
        while True:
            self._db_ready = await self._database.check_connection()
            await asyncio.sleep(_DB_WATCHDOG_INTERVAL_SECONDS)

    async def _start_consumer_with_retry(self, consumer: AIOKafkaConsumer) -> None:
        attempt = 0
        while True:
            try:
                await consumer.start()
                logger.info("Kafka consumer started", extra={"consumer": "data-quality"})
                return
            except KafkaError as exc:
                logger.warning(
                    "Kafka consumer start failed, retrying",
                    extra={"attempt": attempt, "error": str(exc)},
                )
                await asyncio.sleep(
                    compute_backoff(attempt, max_delay_seconds=_KAFKA_START_MAX_BACKOFF_SECONDS)
                )
                attempt += 1

    async def run(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self._settings.kafka_telemetry_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.data_quality_consumer_group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            client_id="lubrisense-data-quality-worker",
        )

        await self._start_consumer_with_retry(self._consumer)
        self._kafka_ready = True
        self._db_ready = await self._database.check_connection()
        self._health_server.start()

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

        topic_task = asyncio.create_task(self._topic_loop())
        window_task = asyncio.create_task(self._window_evaluation_loop())
        watchdog_task = asyncio.create_task(self._db_watchdog_loop())
        try:
            await stop_event.wait()
        finally:
            logger.info("data-quality worker shutting down")
            topic_task.cancel()
            window_task.cancel()
            watchdog_task.cancel()
            await self._consumer.stop()
            await self._database.dispose()
            self._health_server.stop()


async def _main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-data-quality-worker",
    )
    policy = load_quality_policy()
    worker = DataQualityWorker(settings, policy)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
