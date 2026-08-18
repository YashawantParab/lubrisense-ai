"""Kafka -> TimescaleDB consumer worker (Phase 6 brief §5/§9/§18-20; ADR-053/ADR-057).

Runs two concurrent `aiokafka` consumer loops in one process:

- **main-topic loop**: consumes `lubrisense.telemetry.v1` in batches (size/time triggered),
  re-validates + enriches each event, and persists the batch in one transaction via
  `TelemetryRepository.batch_insert_idempotent`. Kafka offsets are committed only *after*
  that transaction commits (`enable_auto_commit=False`) — a transient DB failure retries the
  same uncommitted batch with bounded backoff rather than advancing past it (never silently
  skips messages). An individual message that fails validation or enrichment is written to
  `telemetry_quarantine` instead of `telemetry`, but still counts toward the batch commit.
- **DLQ-topic loop**: consumes `lubrisense.telemetry.dlq.v1` (the bridge's structural
  rejects) and persists each into `telemetry_quarantine` too, so every rejected message is
  visible in one place regardless of which component detected the problem.

Delivery semantics: at-least-once transport, idempotent persistence (see
`app.repositories.telemetry.TelemetryRepository.batch_insert_idempotent`) — this is not a
claim of end-to-end exactly-once.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from aiokafka.errors import KafkaError

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.domain.enums import QuarantineReason, SensorType, TelemetryQuality
from app.infrastructure.database import Database
from app.observability.metrics import WorkerMetrics
from app.observability.worker_health import WorkerHealthServer
from app.pipeline.backoff import compute_backoff
from app.pipeline.enrichment import ContextEnrichmentService, EnrichedContext, EnrichmentFailure
from app.pipeline.validation import SchemaValidator, ValidatedTelemetry, ValidationFailure
from app.repositories.telemetry import TelemetryRepository
from app.repositories.telemetry_quarantine import QuarantineRepository

logger = logging.getLogger("app.pipeline.consumer")

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


@dataclass(frozen=True)
class _DlqIdentity:
    event_id: uuid.UUID | None
    tenant_id: uuid.UUID | None
    sensor_id: uuid.UUID | None
    gateway_id: str | None


def _best_effort_identity(raw: bytes) -> _DlqIdentity:
    """Some DLQ arrivals (e.g. `UNSUPPORTED_SCHEMA_VERSION`) are otherwise well-formed JSON
    — only the version gate rejected them. Recovering the identity fields here (best
    effort, never raises) keeps `telemetry_quarantine` traceable by `event_id` for those
    cases, rather than only by raw payload text (brief §35)."""
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _DlqIdentity(None, None, None, None)
    if not isinstance(parsed, dict):
        return _DlqIdentity(None, None, None, None)

    def _uuid_or_none(value: object) -> uuid.UUID | None:
        if not isinstance(value, str):
            return None
        try:
            return uuid.UUID(value)
        except ValueError:
            return None

    gateway_id = parsed.get("gateway_id")
    return _DlqIdentity(
        event_id=_uuid_or_none(parsed.get("event_id")),
        tenant_id=_uuid_or_none(parsed.get("tenant_id")),
        sensor_id=_uuid_or_none(parsed.get("sensor_id")),
        gateway_id=gateway_id if isinstance(gateway_id, str) else None,
    )


class TelemetryConsumer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._metrics = WorkerMetrics()
        self._validator = SchemaValidator(settings.pipeline_supported_schema_versions_set)
        self._database = Database(settings)

        self._main_consumer: AIOKafkaConsumer | None = None
        self._dlq_consumer: AIOKafkaConsumer | None = None
        self._kafka_ready = False
        self._db_ready = False

        self._health_server = WorkerHealthServer(
            port=settings.telemetry_consumer_health_port,
            service_name="telemetry-consumer",
            readiness_check=self._readiness,
            metrics=self._metrics,
        )

    def _readiness(self) -> tuple[bool, dict[str, str]]:
        details = {
            "kafka": "connected" if self._kafka_ready else "disconnected",
            "database": "reachable" if self._db_ready else "unreachable",
        }
        return self._kafka_ready and self._db_ready, details

    # -- main topic: telemetry ---------------------------------------------------------

    async def _main_topic_loop(self) -> None:
        assert self._main_consumer is not None  # noqa: S101 - set by run() before this task starts
        while True:
            try:
                batches = await self._main_consumer.getmany(
                    timeout_ms=int(self._settings.pipeline_batch_timeout_seconds * 1000),
                    max_records=self._settings.pipeline_batch_size,
                )
                self._kafka_ready = True
            except KafkaError as exc:
                self._kafka_ready = False
                logger.warning("Kafka main-topic fetch failed", extra={"error": str(exc)})
                await asyncio.sleep(2.0)
                continue

            records = [rec for recs in batches.values() for rec in recs]
            if not records:
                continue
            await self._process_main_batch(records)

    async def _process_main_batch(self, records: list[ConsumerRecord]) -> None:
        assert self._main_consumer is not None  # noqa: S101
        attempt = 0
        while True:
            try:
                insert_rows: list[dict[str, object]] = []
                quarantine_ops: list[dict[str, object]] = []

                async with self._database.session() as session:
                    enricher = ContextEnrichmentService(session)
                    for rec in records:
                        result = self._validator.validate(rec.value)
                        if isinstance(result, ValidationFailure):
                            quarantine_ops.append(
                                self._quarantine_kwargs_from_validation(result, rec)
                            )
                            continue
                        enriched = await enricher.enrich(result)
                        if isinstance(enriched, EnrichmentFailure):
                            quarantine_ops.append(
                                self._quarantine_kwargs_from_enrichment(enriched, result, rec)
                            )
                            continue
                        insert_rows.append(self._row_from(result, enriched, rec))

                    telemetry_repo = TelemetryRepository(session)
                    inserted = await telemetry_repo.batch_insert_idempotent(insert_rows)

                    quarantine_repo = QuarantineRepository(session)
                    for kwargs in quarantine_ops:
                        await quarantine_repo.insert(**kwargs)  # type: ignore[arg-type]

                    await session.commit()

                self._db_ready = True
                self._metrics.increment("telemetry_persisted", inserted)
                self._metrics.increment("telemetry_duplicates", len(insert_rows) - inserted)
                self._metrics.increment("telemetry_quarantined", len(quarantine_ops))
                self._metrics.increment("kafka_consumer_messages", len(records))
                self._metrics.set_gauge("batch_size", len(records))

                await self._main_consumer.commit()
                return
            except Exception as exc:  # noqa: BLE001 - top-level retry boundary, see module docstring
                self._db_ready = False
                logger.warning(
                    "main-topic batch persistence failed, retrying without advancing offsets",
                    extra={"attempt": attempt, "batch_size": len(records), "error": str(exc)},
                )
                await asyncio.sleep(
                    compute_backoff(
                        attempt, max_delay_seconds=self._settings.pipeline_retry_max_backoff_seconds
                    )
                )
                attempt += 1

    def _row_from(
        self, event: ValidatedTelemetry, enriched: EnrichedContext, rec: ConsumerRecord
    ) -> dict[str, object]:
        headers = dict(rec.headers or ())
        return {
            "event_id": event.event_id,
            "schema_version": event.schema_version,
            "correlation_id": event.correlation_id,
            "tenant_id": event.tenant_id,
            "site_id": enriched.site_id,
            "plant_id": enriched.plant_id,
            "production_line_id": enriched.production_line_id,
            "machine_id": enriched.machine_id,
            "bearing_id": enriched.bearing_id,
            "lubrication_system_id": enriched.lubrication_system_id,
            "circuit_id": enriched.circuit_id,
            "lubrication_point_id": enriched.lubrication_point_id,
            "sensor_id": event.sensor_id,
            "measurement_type": SensorType(event.measurement_type),
            "value": event.value,
            "unit": event.unit,
            "quality": TelemetryQuality(event.quality),
            "operating_state": event.operating_state,
            "source_timestamp": event.source_timestamp,
            "edge_received_timestamp": event.edge_received_timestamp,
            "edge_emitted_timestamp": event.edge_emitted_timestamp,
            "mqtt_received_timestamp": _parse_header_timestamp(headers, "mqtt_received_timestamp")
            or event.edge_received_timestamp,
            "kafka_published_timestamp": _parse_header_timestamp(
                headers, "kafka_published_timestamp"
            ),
            "consumer_received_timestamp": datetime.now(UTC),
            "sequence_number": event.sequence_number,
            "gateway_id": event.gateway_id,
            "device_id": event.device_id,
            "firmware_version": event.firmware_version,
            "controller_version": event.controller_version,
            "source": event.source,
            "metadata": event.metadata,
            "kafka_partition": rec.partition,
            "kafka_offset": rec.offset,
        }

    @staticmethod
    def _quarantine_kwargs_from_validation(
        failure: ValidationFailure, rec: ConsumerRecord
    ) -> dict[str, object]:
        return {
            "reason": failure.reason,
            "detail": failure.detail,
            "raw_payload": rec.value.decode("utf-8", errors="replace"),
            "kafka_topic": rec.topic,
            "kafka_partition": rec.partition,
            "kafka_offset": rec.offset,
        }

    @staticmethod
    def _quarantine_kwargs_from_enrichment(
        failure: EnrichmentFailure, event: ValidatedTelemetry, rec: ConsumerRecord
    ) -> dict[str, object]:
        return {
            "reason": failure.reason,
            "detail": failure.detail,
            "raw_payload": rec.value.decode("utf-8", errors="replace"),
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "sensor_id": event.sensor_id,
            "gateway_id": event.gateway_id,
            "kafka_topic": rec.topic,
            "kafka_partition": rec.partition,
            "kafka_offset": rec.offset,
        }

    # -- DLQ topic: bridge-detected structural rejects ----------------------------------

    async def _dlq_topic_loop(self) -> None:
        assert self._dlq_consumer is not None  # noqa: S101
        while True:
            try:
                batches = await self._dlq_consumer.getmany(
                    timeout_ms=int(self._settings.pipeline_batch_timeout_seconds * 1000),
                    max_records=self._settings.pipeline_batch_size,
                )
            except KafkaError as exc:
                logger.warning("Kafka DLQ-topic fetch failed", extra={"error": str(exc)})
                await asyncio.sleep(2.0)
                continue

            records = [rec for recs in batches.values() for rec in recs]
            if not records:
                continue
            await self._process_dlq_batch(records)

    async def _process_dlq_batch(self, records: list[ConsumerRecord]) -> None:
        assert self._dlq_consumer is not None  # noqa: S101
        attempt = 0
        while True:
            try:
                async with self._database.session() as session:
                    quarantine_repo = QuarantineRepository(session)
                    for rec in records:
                        headers = dict(rec.headers or ())
                        reason_raw = headers.get("reason", b"SCHEMA_INVALID").decode(
                            "utf-8", errors="replace"
                        )
                        try:
                            reason = QuarantineReason(reason_raw)
                        except ValueError:
                            reason = QuarantineReason.SCHEMA_INVALID
                        detail = headers.get("detail", b"").decode("utf-8", errors="replace")
                        identity = _best_effort_identity(rec.value)
                        await quarantine_repo.insert(
                            reason=reason,
                            detail=detail or "routed via Kafka DLQ topic",
                            raw_payload=rec.value.decode("utf-8", errors="replace"),
                            event_id=identity.event_id,
                            tenant_id=identity.tenant_id,
                            sensor_id=identity.sensor_id,
                            gateway_id=identity.gateway_id,
                            kafka_topic=rec.topic,
                            kafka_partition=rec.partition,
                            kafka_offset=rec.offset,
                        )
                    await session.commit()

                self._db_ready = True
                self._metrics.increment("telemetry_quarantined", len(records))
                await self._dlq_consumer.commit()
                return
            except Exception as exc:  # noqa: BLE001 - top-level retry boundary
                self._db_ready = False
                logger.warning(
                    "DLQ-topic batch persistence failed, retrying without advancing offsets",
                    extra={"attempt": attempt, "batch_size": len(records), "error": str(exc)},
                )
                await asyncio.sleep(
                    compute_backoff(
                        attempt, max_delay_seconds=self._settings.pipeline_retry_max_backoff_seconds
                    )
                )
                attempt += 1

    # -- watchdogs ------------------------------------------------------------------------

    async def _db_watchdog_loop(self) -> None:
        while True:
            self._db_ready = await self._database.check_connection()
            await asyncio.sleep(_DB_WATCHDOG_INTERVAL_SECONDS)

    async def _start_consumer_with_retry(self, consumer: AIOKafkaConsumer, name: str) -> None:
        attempt = 0
        while True:
            try:
                await consumer.start()
                logger.info("Kafka consumer started", extra={"consumer": name})
                return
            except KafkaError as exc:
                logger.warning(
                    "Kafka consumer start failed, retrying",
                    extra={"consumer": name, "attempt": attempt, "error": str(exc)},
                )
                await asyncio.sleep(
                    compute_backoff(attempt, max_delay_seconds=_KAFKA_START_MAX_BACKOFF_SECONDS)
                )
                attempt += 1

    # -- lifecycle ------------------------------------------------------------------------

    async def run(self) -> None:
        self._main_consumer = AIOKafkaConsumer(
            self._settings.kafka_telemetry_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.kafka_consumer_group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            client_id="lubrisense-telemetry-consumer-main",
        )
        self._dlq_consumer = AIOKafkaConsumer(
            self._settings.kafka_dlq_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=f"{self._settings.kafka_consumer_group_id}-dlq",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            client_id="lubrisense-telemetry-consumer-dlq",
        )

        await self._start_consumer_with_retry(self._main_consumer, "main")
        await self._start_consumer_with_retry(self._dlq_consumer, "dlq")
        self._kafka_ready = True
        self._db_ready = await self._database.check_connection()
        self._health_server.start()

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

        main_task = asyncio.create_task(self._main_topic_loop())
        dlq_task = asyncio.create_task(self._dlq_topic_loop())
        watchdog_task = asyncio.create_task(self._db_watchdog_loop())
        try:
            await stop_event.wait()
        finally:
            logger.info("telemetry consumer shutting down")
            main_task.cancel()
            dlq_task.cancel()
            watchdog_task.cancel()
            await self._main_consumer.stop()
            await self._dlq_consumer.stop()
            await self._database.dispose()
            self._health_server.stop()


async def _main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-telemetry-consumer",
    )
    consumer = TelemetryConsumer(settings)
    await consumer.run()


if __name__ == "__main__":
    asyncio.run(_main())
