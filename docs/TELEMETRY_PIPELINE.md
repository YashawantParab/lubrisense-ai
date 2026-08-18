# Telemetry Pipeline — Phase 6 Implementation

Status: PHASE 6 — DRAFT FOR ACCEPTANCE
Last updated: 2026-08-18

This document describes the central telemetry pipeline delivered in Phase 6: MQTT
ingestion, an MQTT → Kafka bridge, a Kafka consumer, TimescaleDB persistence, a read-only
query API, and a minimal frontend validation view — the concrete realization of the
"Platform Ingestion → Kafka" and central-platform responsibilities `docs/ARCHITECTURE.md`
already assigned, and the consumer side of the MQTT topic/QoS contract Phase 5
(`docs/EDGE_ARCHITECTURE.md` §9) already built. It supersedes those documents only in
implementation detail.

Phase 6 is transport, persistence, and query only. It does **not** implement data quality
classification, baselines, rules, feature engineering, ML, Kalman filtering, condition/
decision intelligence, incidents, RAG, agents, or the final product UI — see
`IMPLEMENTATION_STATUS.md` for the phase boundary.

---

## 1. End-to-end data flow

```
Simulator --> Edge --> MQTT (lubrisense/v1/{tenant_id}/{gateway_id}/telemetry, QoS 1)
    --> MQTT-Kafka Bridge --> Kafka (lubrisense.telemetry.v1)
    --> Telemetry Consumer --> TimescaleDB (telemetry hypertable)
    --> Telemetry Query API --> Frontend (minimal validation view)
```

Structurally invalid messages diverge to `lubrisense.telemetry.dlq.v1` at the bridge;
tenant/entity/context failures diverge to the `telemetry_quarantine` table at the consumer.
Both destinations are consumed into one place (`telemetry_quarantine`) so nothing rejected
is invisible — see §12.

Two new worker processes exist alongside the FastAPI backend, all built from the same
`backend/` image (ADR-050): `python -m app.pipeline.mqtt_bridge` and
`python -m app.pipeline.consumer`. Neither runs behind FastAPI — a long-running consume
loop is a different runtime shape than a request handler, so they are not routes.

---

## 2. MQTT ingestion

The bridge subscribes to the wildcard `lubrisense/v1/+/+/telemetry` at QoS 1 — the same
topic hierarchy and QoS the edge already publishes to
(`edge.transport.mqtt.MqttTransport`, ADR-046). `paho-mqtt`'s own network thread
(`loop_start()`) delivers each message; `on_message` hands the raw payload to the bridge's
asyncio loop via `asyncio.run_coroutine_threadsafe` — the two client libraries (paho-mqtt is
thread/callback-based, `aiokafka` is asyncio-based) never share an event loop directly
(ADR-051).

---

## 3. Structural validation

`app.pipeline.validation.SchemaValidator` parses the raw JSON, checks every required field
is present, every UUID/timestamp/enum value is well-formed, and that `schema_version` is in
the supported set (default `{"1"}`, `PIPELINE_SUPPORTED_SCHEMA_VERSIONS`). This is
structural validation only — "is this a well-formed event" — never data-quality
classification (that is Phase 7). A message that fails here cannot be reasoned about at all
and is routed to the Kafka DLQ topic by the bridge.

The central pipeline defines its own copy of the wire contract
(`app.pipeline.contract.TelemetryEnvelope`) rather than importing the `edge` package
(ADR-059) — the two services stay independently deployable. The wire *values* must still
match `edge.domain.envelope.ReadingEnvelope` exactly, since real bytes cross this boundary
unchanged.

---

## 4. MQTT → Kafka bridge

On a structurally valid message, the bridge publishes the **original envelope JSON bytes,
unmodified**, to `lubrisense.telemetry.v1` — `event_id`, `sequence_number`, and every
timestamp are never re-minted (brief requirement: preserve original event identity).
Central ingestion metadata is carried as **Kafka message headers**
(`mqtt_received_timestamp`, `kafka_published_timestamp`), not merged into the payload —
this keeps "preserve identity" and "add central metadata separately" structurally true, not
just a convention.

**Partition key** (ADR-052): `f"{tenant_id}:{gateway_id}:{sensor_id}"`. This preserves
per-sensor-stream ordering within a partition — the only ordering guarantee that matters,
since the flagship demo topology is small enough that Kafka's default single-partition
auto-created topic is sufficient for now (see ADR-006's note to revisit at real fleet
scale/Phase 33).

**Delivery semantics** (ADR-053): at-least-once transport end to end, plus idempotent
persistence — never a claim of exactly-once. `send_and_wait` is wrapped in an explicit
5-second `asyncio.wait_for` with bounded retries: against a broker that is unreachable at
the network/DNS level (not just returning errors), `aiokafka`'s internal metadata-refresh
retry loop can spin past its own `request_timeout_ms` without ever raising back to the
caller — observed directly during the Kafka-outage acceptance test (§10) before this
timeout was added. Without it, an outage would hang the publish path forever instead of
falling through to the durable spool.

**Bridge durability** (ADR-056): if Kafka is unreachable after retries, the message is
written to a dedicated local SQLite spool (`app.pipeline.spool.BridgeSpool`,
`PIPELINE_BRIDGE_SPOOL_PATH`) — separate from the edge's own buffer database (a different
responsibility). A background task drains the spool with bounded backoff once Kafka is
reachable again, oldest-first. Spooling is idempotent on `event_id` (`INSERT OR IGNORE`), so
a redelivered MQTT message never duplicates a pending spool row.

---

## 5. Central timestamp model

Every stage adds its own timestamp, and none of them overwrite the edge's own three
(`source_timestamp`, `edge_received_timestamp`, `edge_emitted_timestamp`):

| Timestamp | Set by |
|---|---|
| `mqtt_received_timestamp` | Bridge, on MQTT receipt |
| `kafka_published_timestamp` | Bridge, on successful Kafka publish (carried as a header) |
| `consumer_received_timestamp` | Consumer, when the batch is pulled from Kafka |
| `persisted_timestamp` | Database, `server_default=now()` at insert |

This lets later analysis (Phase 7+) reason about event time vs. edge time vs. arrival time
vs. persistence time independently — verified directly by the outage tests (§10): a
Kafka-outage-buffered event's `source_timestamp` stays the original acquisition time while
`persisted_timestamp` lands minutes later, after recovery.

---

## 6. Schema versioning

`schema_version` is a required field. Only versions in `PIPELINE_SUPPORTED_SCHEMA_VERSIONS`
(default `{"1"}`) are accepted; anything else is rejected as `UNSUPPORTED_SCHEMA_VERSION`,
distinct from `SCHEMA_INVALID` (malformed/incomplete), so an operator can tell "we don't
support this version yet" from "this message is broken" at a glance in
`telemetry_quarantine`. Adding a new minor/major version is a config change
(`PIPELINE_SUPPORTED_SCHEMA_VERSIONS=1,2`), not a code change, until the new version's shape
actually needs new handling.

---

## 7. TimescaleDB schema and hypertable strategy

The `telemetry` table (migration `1f9fe8b7b163`) carries every field listed in
`docs/EVENT_CATALOG.md` §2.1, plus `kafka_partition`/`kafka_offset` for traceability (§13).
Composite tenant foreign keys (ADR-022 pattern) reference `sensor`/`machine`/`bearing`/
`lubrication_system`/`circuit`/`lubrication_point`/`production_line`/`plant`/`site`, nullable
where the hierarchy field is optional — the same pattern `Sensor` itself uses.

**Hypertable time column** (ADR-054): `source_timestamp` — event time, not an arrival/
persisted timestamp. A replayed or outage-buffered event's `source_timestamp` can be
minutes or hours in the past relative to when it's actually written; partitioning on an
arrival timestamp instead would scatter replayed old events into "now" chunks, defeating
time-range queries over the period they actually describe.

**Chunk interval**: 1 day. A deliberate demo/reference-scale choice for a handful of assets
generating readings on the order of one per few seconds — not a universal recommendation;
revisit under real fleet-scale volume testing (Phase 33).

**Idempotency key** (ADR-053, ADR-054): TimescaleDB requires every unique/primary-key
constraint on a hypertable to include the partitioning column, so the primary key is the
composite `(event_id, source_timestamp)` rather than `event_id` alone. This is safe, not a
weakened guarantee: `event_id` is `uuid5(gateway_id, sensor_id, sequence_number)`, fixed at
edge acquisition and never regenerated (edge ADR-045), so it deterministically implies one
`source_timestamp` already.

---

## 8. Idempotent batch persistence

`TelemetryRepository.batch_insert_idempotent` issues one
`INSERT ... ON CONFLICT (event_id, source_timestamp) DO NOTHING` per batch (ADR-055). The
consumer accumulates a batch via `AIOKafkaConsumer.getmany()` up to `PIPELINE_BATCH_SIZE`
(default 500) or `PIPELINE_BATCH_TIMEOUT_SECONDS` (default 2.0), whichever comes first, then
persists the whole batch in one transaction. Kafka offsets are committed
(`enable_auto_commit=False`) only *after* that transaction commits — a transient DB failure
retries the same batch with bounded backoff and never advances past unpersisted messages
(§10 database-outage test).

---

## 9. Tenant/entity validation and context enrichment

`app.pipeline.enrichment.ContextEnrichmentService` is the one place in the pipeline that
talks to the asset-hierarchy tables — the bridge and `SchemaValidator` are hierarchy-
agnostic by design. Given `tenant_id` + `sensor_id`:

1. The tenant must exist, else `UNKNOWN_TENANT`.
2. The sensor must exist for that tenant, else `UNKNOWN_SENSOR` — this is also how a
   cross-tenant `sensor_id` (real, but belonging to a different tenant) is rejected: the
   lookup is always tenant-scoped, so it simply isn't found.
3. `gateway_id` must resolve to a real, same-tenant `Gateway` row, else `UNKNOWN_GATEWAY`.
   The edge (`edge.acquisition.builder.EnvelopeBuilder`) actually sends `Gateway.id` (a
   UUID) as this wire field's value — not `Gateway.gateway_code`, despite the field name —
   so resolution matches on `Gateway.id` first, falling back to `gateway_code` for a
   producer that reasonably sends the human-readable code instead. Not a foreign key in the
   `telemetry` table itself: the wire contract does not strictly type this field as a UUID.
4. The sensor's single populated attachment column
   (`machine_id`/`bearing_id`/`lubrication_system_id`/`reservoir_id`/`pump_id`/
   `circuit_id` — `Sensor.attached_entity_type`) is walked up through the real hierarchy to
   resolve `site_id`/`plant_id`/`production_line_id`/`machine_id`/`bearing_id`/
   `lubrication_system_id`/`circuit_id` (ADR-058).
5. Any hierarchy field the edge already supplied (currently `machine_id`, and optionally
   `component_id`) is checked against the resolved value — a mismatch is
   `CONTEXT_CONFLICT`, never silently overwritten.

`lubrication_point_id` is not a sensor attachment type, so it stays `NULL` unless a future
phase adds a way to derive it unambiguously — a documented limitation, not an oversight.

---

## 10. Resilience: outage behavior

Both scenarios are exercised end to end by `scripts/verify_pipeline.sh` against the real
Docker Compose stack (stopping/restarting the actual `kafka`/`postgres` containers, not
mocks):

**Kafka outage**: MQTT ingestion continues uninterrupted; the bridge spools durably to
SQLite (§4); `/ready` reports `kafka_producer: degraded` while still returning 200 (a Kafka
outage is "degraded," not "not ready" — the bridge is still doing useful work). On Kafka
recovery, the spool drains automatically; the event lands in TimescaleDB with its original
`source_timestamp` intact and a much later `persisted_timestamp`. No data lost, no
duplicates.

**Database outage**: the Kafka consumer's `/ready` reports 503 (`database: unreachable`)
without crashing; batches already pulled from Kafka are retried with bounded backoff and
their offsets are never committed until a batch actually persists. On DB recovery, pending
batches persist and offsets advance. No data lost, no duplicates (idempotent insert covers
the retried batch even if a partial attempt had side effects).

---

## 11. Duplicate delivery and replay

The same `event_id` can arrive more than once through several independent paths: MQTT QoS 1
redelivery, the bridge's spool-drain retry racing an already-successful publish, Kafka
consumer-group rebalance, or an explicit edge buffer replay
(`docs/EDGE_ARCHITECTURE.md` §8). All of them converge on the same idempotency key
(`event_id`, `source_timestamp`) at insert time (§8) — the database ends up with exactly one
row regardless of how many times the pipeline saw the event, verified directly by
`scripts/verify_pipeline.sh` and `tests/test_telemetry_repository.py`.

---

## 12. DLQ and quarantine

Two destinations, chosen by which component detects the failure (ADR-057):

- **Kafka DLQ topic** (`lubrisense.telemetry.dlq.v1`): the bridge has no database access by
  design (stateless/lightweight) — structural failures it detects (`SCHEMA_INVALID`,
  `UNSUPPORTED_SCHEMA_VERSION`) go here, with `reason`/`detail` as message headers.
- **`telemetry_quarantine` table**: the consumer has database access — tenant/entity/
  context failures it detects (`UNKNOWN_TENANT`, `UNKNOWN_SENSOR`, `UNKNOWN_GATEWAY`,
  `CONTEXT_CONFLICT`) are written here directly.

The consumer also runs a second concurrent `aiokafka` consumer task on the DLQ topic that
drains it into the same `telemetry_quarantine` table, best-effort-recovering `event_id`/
`tenant_id`/`sensor_id`/`gateway_id` from the raw payload where the JSON is otherwise
well-formed (e.g. `UNSUPPORTED_SCHEMA_VERSION` — only the version gate rejected it). This
keeps quarantined events traceable by `event_id` wherever the payload allows it, and every
rejection reachable from one table regardless of which component caught it — nothing is
silently discarded.

---

## 13. Event traceability

Given one `event_id`, it is traceable end to end: the edge's own logs (Phase 5), the Kafka
message (key = partition key, value = the exact envelope bytes), and the `telemetry` row
(`kafka_partition`/`kafka_offset` columns preserve which Kafka message produced it). Verified
directly: publish one event via `scripts/verify_pipeline.sh`, confirm the identical
`event_id` in the resulting row with no regeneration anywhere in the chain.

---

## 14. Query API

Tenant-scoped, read-only, `GET`-only — the primary ingestion path is MQTT/Kafka, not a REST
endpoint (`app/api/v1/telemetry.py`):

- `GET /api/v1/telemetry/sensors/{sensor_id}` — `start`, `end`, `measurement_type`, `limit`
- `GET /api/v1/telemetry/sensors/{sensor_id}/latest`
- `GET /api/v1/telemetry/machines/{machine_id}` — same parameters

Each validates the sensor/machine exists for the tenant first (404 `SENSOR_NOT_FOUND`/
`MACHINE_NOT_FOUND`) before querying, so an empty result always means "no readings yet," not
"wrong id." Internal consumer metadata (Kafka partition/offset) is never exposed in the
response — that stays a pipeline-internal traceability aid.

---

## 15. Frontend validation view

`frontend/src/app/machines/[machineId]/page.tsx` gained a "Recent Telemetry" section
(`useMachineTelemetry`, polling every 10s) — a table of the machine's most recent readings
across all its sensors. This is explicitly the minimal developer/product validation view the
brief calls for, not the final Sensor Intelligence experience: no health score, no
condition, no AI diagnosis, no chart beyond a plain table. Every value shown is a real
backend response (ADR-008) — nothing here is computed in React.

---

## 16. Failure modes not yet handled (Phase 7+)

Structural ingestion requirements only. The following are explicitly out of Phase 6 scope
(brief §46): late/stale/duplicate-*pattern* detection, drift, clock drift, out-of-order
*anomaly* detection, sensor health scoring. Out-of-order arrival is *persistable* (§7's
composite key does not require monotonic insert order) but not yet *detected/classified* —
that is the Phase 7 data-quality engine's job, using the timestamp model this phase
preserves (§5).

---

## 17. Configuration reference

All in `app/core/config.py` / `.env.example`, `# --- Telemetry Pipeline ---` section:
`KAFKA_TELEMETRY_TOPIC`, `KAFKA_DLQ_TOPIC`, `KAFKA_CONSUMER_GROUP_ID`,
`MQTT_TOPIC_PATTERN`, `PIPELINE_BATCH_SIZE`, `PIPELINE_BATCH_TIMEOUT_SECONDS`,
`PIPELINE_RETRY_MAX_BACKOFF_SECONDS`, `PIPELINE_SUPPORTED_SCHEMA_VERSIONS`,
`PIPELINE_BRIDGE_SPOOL_PATH`, `PIPELINE_BRIDGE_SPOOL_DRAIN_INTERVAL_SECONDS`,
`MQTT_BRIDGE_HEALTH_PORT`, `TELEMETRY_CONSUMER_HEALTH_PORT`.

---

## 18. Health, metrics, and Docker Compose

Each worker exposes its own `/health` (liveness — process alive, no dependency calls),
`/ready` (readiness — dependency status, 503 if not ready), and `/metrics` (hand-written
Prometheus text format; no `prometheus_client` dependency yet — full observability is Phase
26) via a small dependency-free `http.server` (`app.pipeline.health`). Counters tracked:
`mqtt_messages_received`, `mqtt_invalid_messages`, `kafka_messages_published`,
`kafka_publish_failures`, `kafka_consumer_messages`, `telemetry_persisted`,
`telemetry_duplicates`, `telemetry_quarantined`, `batch_size`, `bridge_buffer_depth`.

`mqtt-bridge` and `telemetry-consumer` are added to `docker-compose.yml` as **default**
services (no profile gate, unlike `edge`) — they are core platform infrastructure, not an
optional device simulator; `docker compose up -d` starts the whole pipeline.

---

## 19. Known limitations

- Kafka runs single-broker/single-partition-by-default locally (ADR-006, ADR-015) — fine
  for this reference workload, not representative of production replication/partitioning.
- `lubrication_point_id` enrichment is a documented gap (§9) pending a future unambiguous
  derivation path.
- The DLQ-topic quarantine path best-effort-recovers identity fields from otherwise
  well-formed JSON (§12); a genuinely malformed payload (bad JSON) cannot be attributed to
  an `event_id` at all — the raw payload text is still preserved in full.
- No Kafka topic auto-provisioning for a real (non-auto-create) deployment is scripted yet;
  document the manual `kafka-topics.sh --create` invocation here when a non-dev deployment
  profile is added.
